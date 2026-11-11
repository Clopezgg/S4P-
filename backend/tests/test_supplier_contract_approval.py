"""Real API/PG approval, legacy finance guards and transaction fault injection."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.domain.errors import InvalidApprovalStateError
from app.models.approval_request import ApprovalRequest
from app.models.audit import AuditLog
from app.models.supplier import SupplierContract
from app.services import supplier_contract_approval_service
from tests.helpers import (
    approve_supplier_contract,
    create_account,
    create_company,
    create_supplier,
    create_treasury_account,
    login_admin,
    login_as,
)


def _context(client):
    login_admin(client)
    company = create_company(client)
    supplier = create_supplier(client, company_id=company['id'])
    response = client.post('/api/procurement/suppliers/contracts', json={
        'companyId': company['id'], 'supplierId': supplier['id'], 'contractNumber': 'APPROVAL-QA',
        'value': '100', 'currencyCode': 'HNL', 'startDate': '2026-01-01'})
    assert response.status_code == 201, response.text
    contract = response.json()
    response = client.post('/api/master-data/users', json={'companyId': company['id'],
        'email': 'contract-reviewer@example.com', 'fullName': 'Contract reviewer',
        'password': 'Passw0rd!23', 'roleName': 'Finance Manager'})
    assert response.status_code == 201, response.text
    admin = client.get('/api/auth/me').json()
    return company, supplier, contract, response.json(), admin


def test_draft_contract_cannot_post_invoice_or_pay_a_legacy_approved_invoice(client, db_session):
    company, supplier, contract, _, _ = _context(client)
    expense = create_account(client, company_id=company['id'], code='5100', name='Cost', account_type='EXPENSE')
    payable = create_account(client, company_id=company['id'], code='2100', name='AP', account_type='LIABILITY')
    bank_gl = create_account(client, company_id=company['id'], code='1100', name='Cash', account_type='ASSET')
    equity = create_account(client, company_id=company['id'], code='3100', name='Capital', account_type='EQUITY')
    cash = create_treasury_account(client, company_id=company['id'], gl_account_id=bank_gl['id'])
    funding = client.post('/api/treasury/remittances', json={'companyId': company['id'],
        'treasuryAccountId': cash['id'], 'counterAccountId': equity['id'], 'sender': 'QA capital',
        'currencyCode': 'HNL', 'originalAmount': '1000', 'remittanceDate': '2026-01-01'})
    assert funding.status_code == 201, funding.text
    response = client.post('/api/ap/supplier-invoices', json={'companyId': company['id'],
        'supplierId': supplier['id'], 'supplierContractId': contract['id'], 'invoiceNumber': 'QA-DRAFT-GUARD',
        'scope': 'GENERAL', 'expenseAccountId': expense['id'], 'payableAccountId': payable['id'],
        'currencyCode': 'HNL', 'amount': '100', 'invoiceDate': '2026-01-02', 'dueDate': '2026-01-03'})
    assert response.status_code == 201, response.text
    invoice = response.json()
    denied = client.post(f"/api/ap/supplier-invoices/{invoice['id']}/approve")
    assert denied.status_code == 409, denied.text
    assert client.get(f"/api/ap/supplier-invoices/{invoice['id']}").json()['status'] == 'DRAFT'
    approve_supplier_contract(client, contract)
    approved = client.post(f"/api/ap/supplier-invoices/{invoice['id']}/approve")
    assert approved.status_code == 200, approved.text
    # Deliberately emulate a pre-upgrade legacy contract. Financial rows were
    # created through real APIs; no fabricated posting/payment is inserted.
    row = db_session.get(SupplierContract, uuid.UUID(contract['id']))
    row.status = 'DRAFT'
    db_session.commit()
    denied = client.post(f"/api/ap/supplier-invoices/{invoice['id']}/payments", json={
        'treasuryAccountId': cash['id'], 'amount': '100', 'paymentDate': '2026-01-03', 'paymentMethod': 'OTHER'})
    assert denied.status_code == 409, denied.text
    assert client.get(f"/api/ap/supplier-invoices/{invoice['id']}").json()['amountPaid'] == '0.00'
    accounts = client.get(f"/api/treasury/accounts?companyId={company['id']}").json()
    assert next(item['balance'] for item in accounts if item['id'] == cash['id']) == '1000.00'


def test_two_concurrent_submissions_create_one_pending_review(client, db_session):
    company, _, contract, reviewer, admin = _context(client)
    engine = db_session.get_bind()
    barrier = Barrier(2)

    def submit():
        with Session(engine) as session:
            cached = session.get(SupplierContract, uuid.UUID(contract['id']))
            assert cached.status == 'DRAFT'
            barrier.wait(timeout=5)
            try:
                result = supplier_contract_approval_service.submit(session,
                    contract_id=uuid.UUID(contract['id']), requested_by=uuid.UUID(admin['id']),
                    assigned_to=uuid.UUID(reviewer['id']))
                status = result.status
                session.commit()
                return status
            except InvalidApprovalStateError:
                session.rollback()
                return 'CONFLICT'

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: submit(), range(2)))
    assert sorted(results) == ['CONFLICT', 'REVIEW']
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.entity_id == uuid.UUID(contract['id']))) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'procurement.contract.submit')) == 1


def test_actual_audit_failure_rolls_back_contract_and_approval_decision(client, db_session):
    company, _, contract, reviewer, _ = _context(client)
    submitted = client.post(f"/api/procurement/suppliers/contracts/{contract['id']}/submit-for-approval",
                            json={'assignedTo': reviewer['id']})
    assert submitted.status_code == 200, submitted.text
    login_as(client, email=reviewer['email'])
    request = client.get(f"/api/approvals?companyId={company['id']}").json()[0]
    engine = db_session.get_bind()
    with engine.begin() as connection:
        connection.execute(text("""CREATE FUNCTION s4p_qa_reject_contract_audit() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN IF NEW.action = 'procurement.contract.decide' THEN
            RAISE EXCEPTION 'QA contract audit failure'; END IF; RETURN NEW; END $$"""))
        connection.execute(text("CREATE TRIGGER s4p_qa_contract_audit_failure BEFORE INSERT ON audit_logs "
                                "FOR EACH ROW EXECUTE FUNCTION s4p_qa_reject_contract_audit()"))
    try:
        with pytest.raises(DBAPIError, match='QA contract audit failure'):
            client.post(f"/api/approvals/{request['id']}/decide", json={'decision': 'APPROVED'})
        with Session(engine) as session:
            assert session.get(SupplierContract, uuid.UUID(contract['id'])).status == 'REVIEW'
            assert session.get(ApprovalRequest, uuid.UUID(request['id'])).status == 'PENDING'
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == 'procurement.contract.decide')) == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text('DROP TRIGGER s4p_qa_contract_audit_failure ON audit_logs'))
            connection.execute(text('DROP FUNCTION s4p_qa_reject_contract_audit()'))
    decided = client.post(f"/api/approvals/{request['id']}/decide", json={'decision': 'APPROVED'})
    assert decided.status_code == 200, decided.text
