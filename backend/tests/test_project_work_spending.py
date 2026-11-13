"""Real API/PG: a work includes explicitly linked jobs, never unrelated spending."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.domain.errors import InvalidFinancialReferenceError
from app.models.accounting import AccountingDocument, JournalLine
from app.models.idempotency import IdempotencyRecord
from app.models.permission import UserCompanyAccess, UserProjectAccess
from app.models.project import Project
from app.models.project_setup import ProjectSetupRun
from app.repositories import project_repository
from app.schemas.treasury import RemittanceCreateRequest
from app.services import idempotency_service
from tests.helpers import create_company, create_user_with_role, login_admin, login_as
from tests.test_treasury_operations import _setup


def project(client, company, name, parent=None):
    response = client.post('/api/projects', json={
        'companyId': company['id'], 'name': name, 'currencyCode': 'HNL', 'parentProjectId': parent,
    })
    assert response.status_code == 201, response.text
    body = response.json()
    active = client.post(f"/api/projects/{body['id']}/status", json={'status': 'ACTIVE'})
    assert active.status_code == 200, active.text
    return body


def expense(client, company, cash, account, target, amount):
    response = client.post('/api/treasury/general-expenses', json={
        'companyId': company['id'], 'treasuryAccountId': cash['id'], 'expenseAccountId': account['id'],
        'scope': 'PROJECT', 'projectId': target['id'], 'category': 'materiales', 'amount': amount,
        'currencyCode': 'HNL', 'expenseDate': '2026-11-13', 'description': f"Trabajo {target['name']}",
    })
    assert response.status_code == 201, response.text
    return response.json()


def remittance(client, company, cash, capital, target, amount):
    response = client.post('/api/treasury/remittances', json={
        'companyId': company['id'], 'treasuryAccountId': cash['id'], 'counterAccountId': capital['id'],
        'attributedProjectId': target['id'], 'sender': 'Aporte QA', 'currencyCode': 'HNL',
        'originalAmount': amount, 'remittanceDate': '2026-11-13',
    }, headers={'Idempotency-Key': f"work-funding-{target['id']}"})
    return response


def test_house_totals_include_new_linked_work_but_never_others(client, db_session):
    login_admin(client)
    company, cash, account, capital, _ = _setup(client)
    casa = project(client, company, 'Casa residencial')
    verjas = project(client, company, 'Verjas', casa['id'])
    cerco = project(client, company, 'Cerco perimetral', casa['id'])
    otros = project(client, company, 'Otros')
    expense(client, company, cash, account, casa, '10.00')
    expense(client, company, cash, account, verjas, '20.00')
    expense(client, company, cash, account, cerco, '30.00')
    expense(client, company, cash, account, otros, '400.00')
    techo = project(client, company, 'Techo', casa['id'])
    expense(client, company, cash, account, techo, '40.00')
    first = remittance(client, company, cash, capital, casa, '100.00')
    assert first.status_code == 201, first.text
    replay = remittance(client, company, cash, capital, casa, '100.00')
    assert replay.status_code == 201 and replay.json()['id'] == first.json()['id']
    assert remittance(client, company, cash, capital, techo, '50.00').status_code == 201
    assert remittance(client, company, cash, capital, otros, '900.00').status_code == 201

    response = client.get(f"/api/projects/{casa['id']}/spending")
    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body['totalExpenses']) == Decimal('100.00')
    assert Decimal(body['totalRemittances']) == Decimal('150.00')
    assert body['expenseCount'] == 4
    assert {p['name'] for p in body['projects']} == {'Casa residencial', 'Verjas', 'Cerco perimetral', 'Techo'}
    assert otros['id'] not in response.text
    assert Decimal(client.get(f"/api/projects/{otros['id']}/spending").json()['totalExpenses']) == Decimal('400.00')
    assert Decimal(client.get(f"/api/projects/{techo['id']}/spending").json()['totalExpenses']) == Decimal('40.00')
    page = client.get(f"/api/projects/{casa['id']}/spending?limit=1&offset=1").json()
    assert len(page['expenses']) == 1 and page['expenseCount'] == 4
    assert Decimal(page['totalExpenses']) == Decimal('100.00')
    assert client.get(f"/api/projects/{casa['id']}/spending?offset=-1").status_code == 422

    document = db_session.get(AccountingDocument, uuid.UUID(first.json()['accountingDocumentId']))
    assert document.scope == 'CENTRAL' and document.project_id is None
    assert all(line.project_id is None for line in db_session.scalars(select(JournalLine).where(JournalLine.accounting_document_id == document.id)))
    # A formal reversal nets costs to zero; the original remains in the ledger.
    work_cost = client.get(f"/api/projects/{techo['id']}/spending").json()['expenses'][0]
    reversed_cost = client.post(f"/api/accounting/journal-entries/{work_cost['id']}/reverse", json={'reason': 'Corrección QA'})
    assert reversed_cost.status_code == 200, reversed_cost.text
    assert Decimal(client.get(f"/api/projects/{casa['id']}/spending").json()['totalExpenses']) == Decimal('60.00')
    reversed_remittance = client.post(f"/api/accounting/journal-entries/{document.id}/reverse", json={'reason': 'Aporte cancelado QA'})
    assert reversed_remittance.status_code == 200, reversed_remittance.text
    assert Decimal(client.get(f"/api/projects/{casa['id']}/spending").json()['totalRemittances']) == Decimal('50.00')


def test_family_does_not_grant_access_to_unassigned_jobs(client, db_session):
    login_admin(client)
    company, cash, account, _capital, _ = _setup(client)
    casa = project(client, company, 'Casa visible')
    hidden = project(client, company, 'Trabajo restringido', casa['id'])
    expense(client, company, cash, account, casa, '10.00')
    expense(client, company, cash, account, hidden, '99.00')
    user = create_user_with_role(db_session, email='limited-work@example.com', role_name='Finance Manager')
    db_session.add(UserCompanyAccess(user_id=user.id, company_id=uuid.UUID(company['id'])))
    db_session.add(UserProjectAccess(user_id=user.id, project_id=uuid.UUID(casa['id'])))
    db_session.commit()
    login_as(client, email=user.email)
    response = client.get(f"/api/projects/{casa['id']}/spending")
    assert response.status_code == 200, response.text
    assert Decimal(response.json()['totalExpenses']) == Decimal('10.00')
    assert response.json()['scopeLimited'] is True
    assert hidden['id'] not in response.text and 'restringido' not in response.text
    assert client.get(f"/api/projects/{hidden['id']}/spending").status_code == 403


def test_hierarchy_rejects_cross_company_cycles_and_nested_work(client, db_session):
    login_admin(client)
    company = create_company(client)
    casa = project(client, company, 'Casa')
    child = project(client, company, 'Techo', casa['id'])
    foreign = project(client, create_company(client), 'Otra empresa')
    for parent in (child['id'], foreign['id'], casa['id']):
        result = client.patch(f"/api/projects/{casa['id']}", json={'parentProjectId': parent})
        assert result.status_code == 422, result.text
    nested = client.post('/api/projects', json={'companyId': company['id'], 'name': 'Anidado', 'parentProjectId': child['id']})
    assert nested.status_code == 422, nested.text
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(text('UPDATE projects SET parent_project_id=CAST(:parent AS uuid) WHERE id=CAST(:id AS uuid)'), {'parent': foreign['id'], 'id': child['id']})
        db_session.flush()
    assert client.get(f"/api/projects/{casa['id']}").json()['parentProjectId'] is None


def test_remittance_project_reference_is_validated_before_posting(client, db_session):
    login_admin(client)
    company, cash, _account, capital, _ = _setup(client)
    foreign = project(client, create_company(client), 'Ajena')
    before = db_session.scalar(select(text('count(*)')).select_from(AccountingDocument))
    result = remittance(client, company, cash, capital, foreign, '50.00')
    assert result.status_code == 422, result.text
    assert db_session.scalar(select(text('count(*)')).select_from(AccountingDocument)) == before


def test_simultaneous_opposite_links_cannot_create_a_cycle(client, db_session):
    login_admin(client)
    company = create_company(client)
    first = project(client, company, 'Obra A')
    second = project(client, company, 'Obra B')
    barrier = Barrier(2)

    def link(project_id, parent_id):
        with SessionLocal() as session:
            loaded = session.get(Project, uuid.UUID(project_id))
            barrier.wait(timeout=10)
            try:
                project_repository.update_project(session, project=loaded, values={'parent_project_id': uuid.UUID(parent_id)})
                session.commit()
                return 'linked'
            except InvalidFinancialReferenceError:
                session.rollback()
                return 'rejected'

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(link, first['id'], second['id'])
        right = pool.submit(link, second['id'], first['id'])
        assert sorted([left.result(timeout=20), right.result(timeout=20)]) == ['linked', 'rejected']
    with SessionLocal() as session:
        linked = [row for row in session.scalars(select(Project).where(Project.company_id == uuid.UUID(company['id']))) if row.parent_project_id]
        assert len(linked) == 1


def test_legacy_remittance_fingerprint_and_setup_payload_remain_compatible(client, db_session):
    login_admin(client)
    company, cash, _expense, capital, _ = _setup(client)
    request = RemittanceCreateRequest.model_validate({
        'companyId': company['id'], 'treasuryAccountId': cash['id'], 'counterAccountId': capital['id'],
        'sender': 'Aporte sin atribución', 'currencyCode': 'HNL', 'originalAmount': '10.00',
        'remittanceDate': '2026-11-13',
    })
    old_payload = request.model_dump(mode='json', exclude={'attributed_project_id'})
    headers = {'Idempotency-Key': 'legacy-unattributed-remittance'}
    first = client.post('/api/treasury/remittances', json=request.model_dump(mode='json', by_alias=True), headers=headers)
    assert first.status_code == 201, first.text
    record = db_session.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == headers['Idempotency-Key']))
    assert record.payload_hash == idempotency_service._hash_payload(old_payload)
    replay = client.post('/api/treasury/remittances', json=old_payload, headers=headers)
    assert replay.status_code == 201 and replay.json()['id'] == first.json()['id']

    payload = {'project': {'companyId': company['id'], 'name': 'Borrador previo'}, 'wbs': {'code': 'ROOT', 'name': 'Alcance'}, 'activate': False}
    headers = {'Idempotency-Key': 'legacy-project-setup'}
    setup = client.post('/api/projects/setup-runs', json=payload, headers=headers)
    assert setup.status_code == 201, setup.text
    persisted = db_session.get(ProjectSetupRun, uuid.UUID(setup.json()['id']))
    assert 'parent_project_id' not in persisted.payload['project']
    payload['project']['parentProjectId'] = None
    retry = client.post('/api/projects/setup-runs', json=payload, headers=headers)
    assert retry.status_code == 201 and retry.json()['id'] == setup.json()['id']
