"""One residential cycle through the real API and a fully migrated PostgreSQL.

No financial rows are inserted via SQL and no transport/domain mocks are used.
"""
import os
import re
import shutil
import subprocess
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.main import app, create_app
from app.models.accounting import AccountingDocument, JournalLine
from app.models.audit import AuditLog
from app.models.voucher_issuance import VoucherIssuance
from app.models.voucher_verification import VoucherVerification
from app.services.bootstrap_service import bootstrap_admin_if_needed
from tests.helpers import login_admin

BACKEND = Path(__file__).resolve().parents[1]
SLUG = re.sub(r'[^a-z0-9]+', '_', BACKEND.parent.name.lower()).strip('_')
DB_NAME = f'nexora_residential_cycle_{SLUG}'


@pytest.fixture
def migrated_residential_api(client):
    env = {**{k: v for k, v in os.environ.items()
              if k not in {'PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE'}},
           'PGHOST': 'localhost', 'PGPORT': '5432', 'PGUSER': 'nexora',
           'PGPASSWORD': os.environ.get('POSTGRES_PASSWORD', 'nexora')}
    url = f"postgresql+psycopg://nexora:{env['PGPASSWORD']}@localhost:5432/{DB_NAME}"
    subprocess.run(['dropdb', '--if-exists', DB_NAME], env=env, check=True)
    subprocess.run(['createdb', DB_NAME], env=env, check=True)
    engine = create_engine(url)
    previous_override = app.dependency_overrides[get_db]
    try:
        upgrade = subprocess.run(
            [shutil.which('alembic') or str(BACKEND / '.venv/bin/alembic'), 'upgrade', 'head'],
            cwd=BACKEND, env={**env, 'DATABASE_URL': url,
                             'BOOTSTRAP_ADMIN_EMAIL': '', 'BOOTSTRAP_ADMIN_PASSWORD': ''},
            capture_output=True, text=True, timeout=120,
        )
        assert upgrade.returncode == 0, upgrade.stderr
        with Session(engine) as session:
            bootstrap_admin_if_needed(session)

        def target_db():
            with Session(engine, autoflush=False) as session:
                yield session

        app.dependency_overrides[get_db] = target_db
        yield client, engine, target_db
    finally:
        app.dependency_overrides[get_db] = previous_override
        engine.dispose()
        if os.environ.get('S4P_KEEP_RESIDENTIAL_QA') != '1':
            subprocess.run(['dropdb', '--if-exists', DB_NAME], env=env, check=True)


def test_residential_cycle_approval_payment_pdf_reconciliation_reversal(migrated_residential_api, tmp_path):
    client, engine, target_db = migrated_residential_api

    def call(method, path, payload=None, *, code=200, key=None):
        headers = {'Idempotency-Key': key} if key else {}
        result = client.request(method, '/api' + path, json=payload, headers=headers)
        assert result.status_code == code, f'{method} {path}: {result.text}'
        return result.json() if result.content else None

    def balance(account_id):
        rows = call('GET', f"/treasury/accounts?companyId={company['id']}")
        return Decimal(next(r['balance'] for r in rows if r['id'] == account_id))

    def login(email):
        call('POST', '/auth/logout', code=204)
        call('POST', '/auth/login', {'email': email, 'password': 'ResidentialQA123!'})

    login_admin(client)
    company = call('POST', '/master-data/companies',
                   {'name': 'S4P residential cycle QA', 'functionalCurrencyCode': 'HNL'}, code=201)
    foreign = call('POST', '/master-data/companies',
                   {'name': 'S4P isolated foreign QA', 'functionalCurrencyCode': 'HNL'}, code=201)
    setup_payload = {
        'project': {'companyId': company['id'], 'name': 'Residential QA 13 phases',
                    'code': 'QA-RES-13', 'currencyCode': 'HNL',
                    'plannedStart': '2026-01-01', 'plannedEnd': '2026-12-31'},
        'wbsTemplate': 'RESIDENTIAL_HOUSE_V1', 'baselineAmount': '10000.00', 'activate': True,
    }
    setup = call('POST', '/projects/setup-runs', setup_payload, code=201, key='residential-setup')
    assert call('POST', '/projects/setup-runs', setup_payload, code=201, key='residential-setup')['id'] == setup['id']
    completed = call('POST', f"/projects/setup-runs/{setup['id']}/execute")
    project_id = completed['projectId']
    assert call('POST', f"/projects/setup-runs/{setup['id']}/execute")['projectId'] == project_id
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM wbs_nodes WHERE project_id=CAST(:id AS uuid)'), {'id': project_id}) == 14
        assert conn.scalar(text("SELECT status FROM projects WHERE id=CAST(:id AS uuid)"), {'id': project_id}) == 'ACTIVE'
        assert conn.scalar(text('SELECT sum(l.authorized_amount) FROM budget_lines l JOIN budgets b ON b.id=l.budget_id WHERE b.project_id=CAST(:id AS uuid)'), {'id': project_id}) == Decimal('10000')
        assert conn.scalar(text('SELECT count(*) FROM accounting_documents')) == 0

    def account(code, kind):
        return call('POST', '/master-data/accounts', {'companyId': company['id'],
                    'code': code, 'name': f'QA {kind} {code}', 'accountType': kind}, code=201)

    cash_gl, bank_gl = account('1110', 'ASSET'), account('1120', 'ASSET')
    equity, expense, payable = account('3100', 'EQUITY'), account('5100', 'EXPENSE'), account('2100', 'LIABILITY')
    cash = call('POST', '/treasury/accounts', {'companyId': company['id'], 'name': 'QA Cash',
                'kind': 'CASH', 'currencyCode': 'HNL', 'glAccountId': cash_gl['id']}, code=201)
    bank = call('POST', '/treasury/accounts', {'companyId': company['id'], 'name': 'QA Bank',
                'kind': 'BANK', 'currencyCode': 'HNL', 'glAccountId': bank_gl['id']}, code=201)
    funding = {'companyId': company['id'], 'treasuryAccountId': cash['id'],
               'counterAccountId': equity['id'], 'originType': 'CAPITAL_CONTRIBUTION',
               'sender': 'Isolated QA contribution', 'reference': 'QA-GENERAL-FUND', 'currencyCode': 'HNL',
               'originalAmount': '10000.00', 'remittanceDate': '2026-10-01'}
    remittance = call('POST', '/treasury/remittances', funding, code=201, key='residential-funding')
    assert call('POST', '/treasury/remittances', funding, code=201, key='residential-funding')['id'] == remittance['id']
    assert balance(cash['id']) == Decimal('10000') and balance(bank['id']) == 0

    supplier = call('POST', '/procurement/suppliers',
                    {'companyId': company['id'], 'legalName': 'Residential QA contractor'}, code=201)
    contract = call('POST', '/procurement/suppliers/contracts', {
        'companyId': company['id'], 'supplierId': supplier['id'], 'projectId': project_id,
        'contractNumber': 'QA-RES-CONTRACT', 'value': '1000.00', 'currencyCode': 'HNL',
        'startDate': '2026-10-01', 'retentionPercentage': '0',
    }, code=201)
    schedule = call('POST', '/contract-payments/schedules', {
        'supplierContractId': contract['id'], 'scheduleType': 'CUSTOM',
        'installments': [{'periodYear': 2026, 'periodMonth': 10, 'dueDate': '2026-10-15',
                          'scheduledAmount': '1000.00'}],
    }, code=201)
    installment_id = schedule['installments'][0]['installmentId']
    invoice_payload = {
        'companyId': company['id'], 'supplierId': supplier['id'], 'invoiceNumber': 'QA-RES-INVOICE',
        'scope': 'PROJECT', 'projectId': project_id, 'expenseAccountId': expense['id'],
        'payableAccountId': payable['id'], 'currencyCode': 'HNL', 'amount': '1000.00',
        'invoiceDate': '2026-10-10', 'dueDate': '2026-10-15',
        'supplierContractId': contract['id'], 'contractInstallmentId': installment_id,
    }
    invoice = call('POST', '/ap/supplier-invoices', invoice_payload, code=201)
    call('POST', '/ap/supplier-invoices', invoice_payload, code=422)
    approver = executor = outsider = None
    for label, owner in [('approver', company), ('executor', company), ('outsider', foreign)]:
        person = call('POST', '/master-data/users', {'companyId': owner['id'],
                      'email': f'residential-{label}@example.com', 'fullName': f'QA {label}',
                      'password': 'ResidentialQA123!', 'roleName': 'Finance Manager'}, code=201)
        if label != 'outsider':
            call('PUT', f"/access-management/users/{person['id']}/projects/{project_id}")
        if label == 'approver':
            approver = person
        elif label == 'executor':
            executor = person
        else:
            outsider = person
    # A company member without project assignment cannot inspect its contract.
    unassigned = call('POST', '/master-data/users', {'companyId': company['id'],
        'email': 'residential-unassigned@example.com', 'fullName': 'QA unassigned',
        'password': 'ResidentialQA123!', 'roleName': 'Finance Manager'}, code=201)
    auditor = call('POST', '/master-data/users', {'companyId': company['id'],
        'email': 'residential-auditor@example.com', 'fullName': 'QA auditor',
        'password': 'ResidentialQA123!', 'roleName': 'Auditor'}, code=201)
    login(unassigned['email'])
    assert call('GET', f"/projects?company_id={company['id']}") == []
    assert call('GET', '/accounting/documents/lookup?q=QA-RES')['results'] == []
    assert any(r['entityType'] == 'REMITTANCE' for r in
               call('GET', '/accounting/documents/lookup?q=QA-GENERAL-FUND')['results'])
    call('GET', f"/contract-payments/by-contract/{contract['id']}", code=403)
    call('GET', f"/contract-payments/schedules/{schedule['id']}/summary", code=403)
    login(auditor['email'])
    call('GET', f"/contract-payments/by-contract/{contract['id']}")
    call('POST', '/contract-payments/schedules', {
        'supplierContractId': contract['id'], 'scheduleType': 'CUSTOM',
        'installments': [{'periodYear': 2026, 'periodMonth': 11, 'dueDate': '2026-11-15',
                          'scheduledAmount': '1000.00'}]}, code=403)
    call('POST', f"/contract-payments/schedules/{schedule['id']}/retention-releases",
         {'amount': '1.00', 'dueDate': '2026-11-15', 'reason': 'QA negative'}, code=403)
    login_admin(client)
    call('POST', f"/ap/supplier-invoices/{invoice['id']}/submit-for-approval", {'assignedTo': approver['id']})
    with engine.connect() as conn:
        approval_id = str(conn.scalar(text('SELECT id FROM approval_requests WHERE entity_id=CAST(:id AS uuid)'), {'id': invoice['id']}))
    call('POST', f'/approvals/{approval_id}/decide', {'decision': 'APPROVED'}, code=403)
    call('POST', f"/ap/supplier-invoices/{invoice['id']}/approve", code=409)
    login(approver['email'])
    call('POST', f'/approvals/{approval_id}/decide', {'decision': 'APPROVED'})
    login(executor['email'])
    assert [p['id'] for p in call('GET', f"/projects?company_id={company['id']}")] == [project_id]
    call('GET', f"/projects?company_id={foreign['id']}", code=403)
    payment_payload = {'treasuryAccountId': cash['id'], 'amount': '1000.00',
                       'paymentDate': '2026-10-15', 'paymentMethod': 'CASH',
                       'bankTransactionReference': 'QA-RES-BANK-REF',
                       'contractAllocations': [{'installmentId': installment_id, 'amountApplied': '1000.00'}]}
    call('POST', f"/ap/supplier-invoices/{invoice['id']}/payments",
         {**payment_payload, 'contractAllocations': []}, code=422)
    payment = call('POST', f"/ap/supplier-invoices/{invoice['id']}/payments", payment_payload, code=201, key='residential-payment')
    assert call('POST', f"/ap/supplier-invoices/{invoice['id']}/payments", payment_payload, code=201, key='residential-payment')['id'] == payment['id']
    call('POST', f"/ap/supplier-invoices/{invoice['id']}/payments", {**payment_payload, 'amount': '999.00'}, code=409, key='residential-payment')
    assert balance(cash['id']) == Decimal('9000')
    assert call('GET', f"/ap/supplier-invoices/{invoice['id']}")['status'] == 'PAID'
    assert call('GET', f"/contract-payments/by-contract/{contract['id']}")['installments'][0]['paid'] == '1000.00'

    login_admin(client)
    call('PATCH', f"/master-data/companies/{company['id']}", {'voucherApproverName': 'QA approved signature name'})
    pdf_path = f"/treasury/vouchers/{payment['accountingDocumentId']}?beneficiary=Residential%20QA&paymentMethod=Efectivo"
    pdf = client.get('/api' + pdf_path)
    assert pdf.status_code == 200, pdf.text
    assert b'QA-RES-CONTRACT' in pdf.content
    assert b'Pagos del contrato a la fecha' in pdf.content
    (tmp_path / 'contractual-voucher.pdf').write_bytes(pdf.content)
    assert len(re.findall(rb'/Type\s*/Page\b', pdf.content)) == 2
    assert len(re.findall(rb'/MediaBox\s*\[\s*0\s+0\s+612\s+792\s*\]', pdf.content)) == 2
    with Session(engine) as session:
        token = session.scalar(select(VoucherVerification).where(
            VoucherVerification.accounting_document_id == uuid.UUID(payment['accountingDocumentId'])))
        verification_url = f'/verificar/comprobante/{token.token}'
        receipt_number, receipt_code = token.document_number, token.verification_code
    assert verification_url.encode() in pdf.content
    original_verification = call('GET', verification_url)
    assert original_verification['verified'] is True
    with Session(engine) as session:
        issued = session.scalar(select(VoucherIssuance))
        original_context = issued.contract_context_snapshot
        assert original_context['history'][0]['paid'] == '1000.00'
    # Real DDL rollback/re-upgrade must retain an already issued snapshot.
    from release_maintenance import schema_roundtrip
    assert schema_roundtrip(engine)
    login(unassigned['email'])
    for query in [receipt_number, receipt_code, 'QA-RES-BANK-REF']:
        assert call('GET', f'/accounting/documents/lookup?q={query}')['results'] == []
    login(executor['email'])
    visible = call('GET', '/accounting/documents/lookup?q=QA-RES-BANK-REF')['results']
    assert any(r['entityType'] == 'SUPPLIER_PAYMENT' and r['id'] == payment['id'] for r in visible)
    login_admin(client)

    statement = call('POST', '/treasury/bank-statements', {'treasuryAccountId': cash['id'],
                      'statementDate': '2026-10-31', 'openingBalance': '10000.00', 'closingBalance': '9000.00'}, code=201)
    line = call('POST', f"/treasury/bank-statements/{statement['id']}/lines", {
        'lineDate': '2026-10-15', 'description': 'QA contractual payment', 'amount': '-1000.00'}, code=201)
    matched = call('POST', f"/treasury/bank-statement-lines/{line['id']}/match", {
        'accountingDocumentId': payment['accountingDocumentId'], 'matchedAmount': '1000.00'})
    assert matched['status'] == 'MATCHED'
    assert call('POST', f"/treasury/bank-statement-lines/{line['id']}/unmatch")['status'] == 'UNMATCHED'
    login(outsider['email'])
    assert call('GET', '/accounting/documents/lookup?q=QA-RES')['results'] == []
    call('GET', f"/ap/supplier-invoices/{invoice['id']}", code=403)
    call('GET', pdf_path, code=403)
    login(executor['email'])
    reversal_path = f"/ap/supplier-payments/{payment['id']}/reverse"
    reversal = call('POST', reversal_path, {'reason': 'Isolated QA reversal after reconciliation correction'})
    call('POST', reversal_path, {'reason': 'Rejected second reversal'}, code=409)
    assert reversal['invoiceStatus'] == 'APPROVED'
    # Resolve the live GL status before any PDF reprint.
    assert call('GET', verification_url)['status'] == 'REVERSED'
    reprinted = client.get('/api' + pdf_path)
    assert reprinted.status_code == 200, reprinted.text
    assert b'QA-RES-CONTRACT' in reprinted.content
    assert b'Pagos del contrato a la fecha' in reprinted.content
    assert len(re.findall(rb'/Type\s*/Page\b', reprinted.content)) == 2
    with Session(engine) as session:
        issued = session.scalar(select(VoucherIssuance))
        assert issued.contract_context_snapshot == original_context
        # Emulate a legacy issuance with no stored installment history.
        # This deliberate compatibility fixture touches isolated QA only.
        issued.contract_context_snapshot = None
        session.commit()
    legacy = client.get('/api' + pdf_path)
    assert legacy.status_code == 200, legacy.text
    assert b'QA-RES-CONTRACT' in legacy.content
    assert b'no registrado' in legacy.content
    assert call('GET', verification_url) == {**original_verification, 'status': 'REVERSED'}
    assert balance(cash['id']) == Decimal('10000')
    assert call('GET', f"/contract-payments/by-contract/{contract['id']}")['installments'][0]['paid'] == '0.00'
    with Session(engine) as session:
        docs = list(session.scalars(select(AccountingDocument)))
        assert len(docs) == 4
        for doc in docs:
            lines = list(session.scalars(select(JournalLine).where(JournalLine.accounting_document_id == doc.id)))
            assert sum((v.debit_amount for v in lines), Decimal(0)) == sum((v.credit_amount for v in lines), Decimal(0)) > 0
        actions = set(session.scalars(select(AuditLog.action)))
        assert {'project.setup.complete', 'ap.supplier_invoice.create', 'workflow.approval.decide',
                'ap.supplier_payment.create', 'ap.supplier_payment.reverse',
                'treasury.bank_reconciliation.unmatch'}.issubset(actions)
        assert session.scalar(text('SELECT version_num FROM alembic_version')) == 'dae6224cb8be'
    restarted = create_app()
    restarted.dependency_overrides[get_db] = target_db
    with TestClient(restarted) as new_client:
        new_client.cookies.update(client.cookies)
        assert new_client.get('/api/auth/me').json()['id'] == executor['id']
        saved = new_client.get(f"/api/ap/supplier-invoices/{invoice['id']}")
        assert saved.status_code == 200 and saved.json()['amountPaid'] == '0.00'
        assert new_client.get('/api' + verification_url).json()['verified'] is True
