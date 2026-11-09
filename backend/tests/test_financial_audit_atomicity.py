"""Real PostgreSQL fault injection: business writes and audit are one unit."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.accounting import AccountingDocument, JournalLine
from app.models.ap import SupplierInvoice, SupplierPayment
from app.models.approval_request import ApprovalRequest
from app.models.ar import CustomerInvoice, CustomerReceipt
from app.models.audit import AuditLog
from app.models.idempotency import IdempotencyRecord
from app.models.notification import Notification
from app.models.treasury import CashClosing, Remittance
from app.services import audit_service
from tests.helpers import (
    create_account,
    create_customer,
    create_user_with_role,
    login_admin,
    login_as,
)
from tests.test_ap_ar import _setup_ap
from tests.test_treasury_operations import _setup


def _snapshot(engine):
    models = (AccountingDocument, JournalLine, SupplierInvoice, SupplierPayment,
              CustomerInvoice, CustomerReceipt, CashClosing, Remittance,
              AuditLog, IdempotencyRecord, ApprovalRequest, Notification)
    with Session(engine) as session:
        return {model.__tablename__: list(session.execute(
            select(model.__table__).order_by(model.id),
        ).tuples()) for model in models}


def _invoice(client, kind, *, approve=False):
    company, bank, expense, payable, supplier = _setup_ap(client)
    if kind == 'ap':
        payload = {
            'companyId': company['id'], 'supplierId': supplier['id'],
            'invoiceNumber': 'ATOMIC-AP', 'scope': 'GENERAL',
            'expenseAccountId': expense['id'], 'payableAccountId': payable['id'],
            'currencyCode': 'HNL', 'amount': '100.00', 'invoiceDate': '2026-01-10',
        }
        path = '/api/ap/supplier-invoices'
    else:
        customer = create_customer(client, company_id=company['id'])
        revenue = create_account(client, company_id=company['id'], code='4100', name='Revenue QA', account_type='REVENUE')
        receivable = create_account(client, company_id=company['id'], code='1200', name='Receivable QA', account_type='ASSET')
        payload = {
            'companyId': company['id'], 'customerId': customer['id'],
            'invoiceNumber': 'ATOMIC-AR', 'scope': 'GENERAL',
            'revenueAccountId': revenue['id'], 'receivableAccountId': receivable['id'],
            'currencyCode': 'HNL', 'amount': '100.00', 'invoiceDate': '2026-01-10',
        }
        path = '/api/ar/customer-invoices'
    payload['dueDate'] = '2026-02-10'
    created = client.post(path, json=payload)
    assert created.status_code == 201, created.text
    invoice = created.json()
    if approve:
        approved = client.post(f"{path}/{invoice['id']}/approve")
        assert approved.status_code == 200, approved.text
    return f"{path}/{invoice['id']}", bank


@pytest.mark.parametrize('operation,keyed', [
    (operation, keyed)
    for operation in ('remittance', 'ap_payment', 'ar_receipt', 'cash_closing')
    for keyed in (False, True)
] + [(operation, False) for operation in ('ap_approve', 'ap_cancel', 'ap_submit', 'ar_approve')])
def test_financial_command_rolls_back_if_its_audit_fails(client, db_session, monkeypatch, operation, keyed):
    login_admin(client)
    if operation.startswith('ap_') or operation.startswith('ar_'):
        kind = operation[:2]
        path, bank = _invoice(client, kind, approve=operation in ('ap_payment', 'ar_receipt'))
        payload = {}
        if operation == 'ap_payment':
            url, action = path + '/payments', 'ap.supplier_payment.create'
            payload = {'treasuryAccountId': bank['id'], 'amount': '25.00', 'paymentDate': '2026-01-20'}
        elif operation == 'ar_receipt':
            url, action = path + '/receipts', 'ar.customer_receipt.create'
            payload = {'treasuryAccountId': bank['id'], 'amount': '100.00', 'receiptDate': '2026-01-20'}
        elif operation == 'ap_submit':
            approver = create_user_with_role(db_session, email='atomic-approver@example.com', role_name='Administrator')
            url, action = path + '/submit-for-approval', 'ap.supplier_invoice.submit'
            payload = {'assignedTo': str(approver.id)}
        else:
            verb = operation.split('_')[1]
            url, action = path + '/' + verb, f'{kind}.supplier_invoice.{verb}' if kind == 'ap' else f'ar.customer_invoice.{verb}'
    else:
        company, cash, difference, equity, _ = _setup(client)
        if operation == 'remittance':
            url, action = '/api/treasury/remittances', 'treasury.remittance.create'
            payload = {'companyId': company['id'], 'treasuryAccountId': cash['id'],
                       'counterAccountId': equity['id'], 'sender': 'Atomic QA',
                       'currencyCode': 'HNL', 'originalAmount': '75.00', 'remittanceDate': '2026-01-20'}
        else:
            closing = client.post('/api/treasury/cash-closings', json={
                'treasuryAccountId': cash['id'], 'closingDate': '2026-01-31',
                'openingAmount': '1000.00', 'expectedAmount': '1000.00', 'countedAmount': '980.00',
            })
            assert closing.status_code == 201, closing.text
            url = f"/api/treasury/cash-closings/{closing.json()['id']}/approve?companyId={company['id']}"
            action, payload = 'treasury.cash_closing.approve', {'differenceAccountId': difference['id']}
    db_session.commit()
    engine = db_session.get_bind()
    before = _snapshot(engine)
    original = audit_service.record

    def fail_target_audit(*args, **kwargs):
        if kwargs.get('action') == action:
            raise RuntimeError('injected audit write failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(audit_service, 'record', fail_target_audit)
    headers = {'Idempotency-Key': 'atomic-audit-qa'} if keyed else {}
    with pytest.raises(RuntimeError, match='injected audit write failure'):
        client.post(url, json=payload, headers=headers)
    # The production get_db finalizer closes/rolls back. The test override keeps
    # its Session open, so emulate that finalizer before reading a NEW connection.
    db_session.rollback()
    assert _snapshot(engine) == before


def test_partial_customer_receipt_persists_its_full_status(client, db_session):
    login_admin(client)
    path, bank = _invoice(client, 'ar', approve=True)
    partial = client.post(path + '/receipts', json={
        'treasuryAccountId': bank['id'], 'amount': '25.00', 'receiptDate': '2026-01-20',
    })
    assert partial.status_code == 201, partial.text
    db_session.expire_all()
    invoice = client.get(path).json()
    assert invoice['status'] == 'PARTIALLY_COLLECTED'
    assert invoice['amountCollected'] == '25.00'
    final = client.post(path + '/receipts', json={
        'treasuryAccountId': bank['id'], 'amount': '75.00', 'receiptDate': '2026-01-21',
    })
    assert final.status_code == 201, final.text
    assert client.get(path).json()['status'] == 'COLLECTED'


def test_admin_can_cancel_draft_and_update_payment_reference_but_auditor_cannot(client, db_session):
    login_admin(client)
    path, bank = _invoice(client, 'ap', approve=True)
    payment = client.post(path + '/payments', json={
        'treasuryAccountId': bank['id'], 'amount': '25.00', 'paymentDate': '2026-01-20',
    })
    assert payment.status_code == 201, payment.text
    url = f"/api/ap/supplier-payments/{payment.json()['id']}"
    updated = client.patch(url, json={'bankTransactionReference': 'QA-REF'})
    assert updated.status_code == 200, updated.text
    assert updated.json()['bankTransactionReference'] == 'QA-REF'
    draft_path, _ = _invoice(client, 'ap')
    cancelled = client.post(draft_path + '/cancel')
    assert cancelled.status_code == 200, cancelled.text
    assert client.get(draft_path).json()['status'] == 'CANCELLED'
    auditor = create_user_with_role(db_session, email='atomic-auditor@example.com', role_name='Auditor')
    login_as(client, email=auditor.email)
    assert client.patch(url, json={'bankTransactionReference': 'UNAUTHORIZED'}).status_code == 403
    login_admin(client)
    assert client.get(path + '/payments').json()[0]['bankTransactionReference'] == 'QA-REF'
