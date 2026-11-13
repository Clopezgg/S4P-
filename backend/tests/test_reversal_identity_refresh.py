"""Independent PostgreSQL sessions retain objects loaded before another reversal."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.domain.errors import InvalidInvoiceStateError
from app.models.accounting import AccountingDocument, JournalLine
from app.models.ap import SupplierInvoice, SupplierPayment
from app.models.ar import CustomerInvoice, CustomerReceipt
from app.models.treasury import CashClosing
from app.services import payment_receipt_reversal_service as reversals
from app.services import treasury_service
from tests.helpers import (
    create_account,
    create_company,
    create_customer,
    create_treasury_account,
    login_admin,
)
from tests.test_payment_receipt_reversals import _funded_ap_context
from tests.test_treasury_operations import _setup as treasury_setup


def _setup(client, kind):
    if kind == "ap":
        company, bank, expense, payable, supplier = _funded_ap_context(client)
        party = {"supplierId": supplier["id"], "expenseAccountId": expense["id"], "payableAccountId": payable["id"]}
        invoices, payments, date_key = "ap/supplier-invoices", "payments", "paymentDate"
    else:
        company = create_company(client)
        gl = create_account(client, company_id=company["id"], code="1100", name="Banco", account_type="ASSET")
        receivable = create_account(client, company_id=company["id"], code="1200", name="CxC", account_type="ASSET")
        revenue = create_account(client, company_id=company["id"], code="4100", name="Ingreso", account_type="REVENUE")
        bank = create_treasury_account(client, company_id=company["id"], gl_account_id=gl["id"])
        customer = create_customer(client, company_id=company["id"])
        party = {"customerId": customer["id"], "receivableAccountId": receivable["id"], "revenueAccountId": revenue["id"]}
        invoices, payments, date_key = "ar/customer-invoices", "receipts", "receiptDate"
    response = client.post(f"/api/{invoices}", json={
        "companyId": company["id"], "invoiceNumber": f"CACHED-REV-{kind}", "scope": "GENERAL",
        "currencyCode": "HNL", "amount": "1000.00", "invoiceDate": "2026-08-02", "dueDate": "2026-09-02", **party,
    })
    assert response.status_code == 201, response.text
    invoice_id = response.json()["id"]
    approved = client.post(f"/api/{invoices}/{invoice_id}/approve")
    assert approved.status_code == 200, approved.text
    entries = []
    for amount in ("400.00", "600.00"):
        response = client.post(f"/api/{invoices}/{invoice_id}/{payments}", json={
            "treasuryAccountId": bank["id"], "amount": amount, date_key: "2026-08-03",
        })
        assert response.status_code == 201, response.text
        entries.append(response.json())
    return invoice_id, entries


@pytest.mark.parametrize("kind", ["ap", "ar"])
@pytest.mark.parametrize("same_entry", [False, True], ids=["different-partial-reversals", "duplicate-reversal"])
def test_reversal_refreshes_all_preloaded_financial_state(client, db_session, kind, same_entry):
    login_admin(client)
    actor_id = uuid.UUID(client.get("/api/auth/me").json()["id"])
    invoice_id, entries = _setup(client, kind)
    invoice_model, entry_model, field, service, route = (
        (SupplierInvoice, SupplierPayment, "amount_paid", reversals.reverse_supplier_payment, "ap/supplier-payments")
        if kind == "ap" else
        (CustomerInvoice, CustomerReceipt, "amount_collected", reversals.reverse_customer_receipt, "ar/customer-receipts")
    )
    entry_id = uuid.UUID(entries[0]["id"])
    with SessionLocal() as stale:
        # Keep strong references: SQLAlchemy's identity map is weak by default.
        loaded_invoice = stale.get(invoice_model, uuid.UUID(invoice_id))
        loaded_entry = stale.get(entry_model, entry_id)
        loaded_document = stale.get(AccountingDocument, loaded_entry.accounting_document_id)
        assert getattr(loaded_invoice, field) == Decimal("1000.00")
        assert loaded_document.status == "POSTED"
        other = entries[0 if same_entry else 1]["id"]
        response = client.post(f"/api/{route}/{other}/reverse", json={"reason": "Otra sesión confirma primero"})
        assert response.status_code == 200, response.text
        # Before the service's lock, our live ORM objects still contain old data.
        assert getattr(loaded_invoice, field) == Decimal("1000.00")
        args = {"payment_id" if kind == "ap" else "receipt_id": entry_id,
                "reason": "Reversión con entidades precargadas", "actor_user_id": actor_id}
        if same_entry:
            with pytest.raises(InvalidInvoiceStateError, match="ya fue revertido"):
                service(stale, **args)
            stale.rollback()
        else:
            service(stale, **args)
    with SessionLocal() as check:
        persisted = check.get(invoice_model, uuid.UUID(invoice_id))
        assert getattr(persisted, field) == (Decimal("600.00") if same_entry else Decimal("0.00"))
        assert persisted.status == (("PARTIALLY_PAID" if kind == "ap" else "PARTIALLY_COLLECTED") if same_entry else "APPROVED")
        documents = []
        for entry in entries:
            record = check.get(entry_model, uuid.UUID(entry["id"]))
            documents.append(record.accounting_document_id)
            expected_reversed = not same_entry or record.id == entry_id
            assert (record.reversed_at is not None) == expected_reversed
            assert (record.reversal_accounting_document_id is not None) == expected_reversed
            if record.reversal_accounting_document_id:
                documents.append(record.reversal_accounting_document_id)
        assert len(documents) == (3 if same_entry else 4)
        balances = {}
        for line in check.scalars(select(JournalLine).where(JournalLine.accounting_document_id.in_(documents))):
            balances[line.account_id] = balances.get(line.account_id, Decimal("0")) + line.debit_amount - line.credit_amount
        assert sorted(balances.values()) == ([Decimal("-600.00"), Decimal("600.00")] if same_entry else [Decimal("0.00"), Decimal("0.00")])
        reversals_in_company = list(check.scalars(select(AccountingDocument).where(
            AccountingDocument.company_id == persisted.company_id, AccountingDocument.document_type_code == "ANU",
        )))
        assert len(reversals_in_company) == (1 if same_entry else 2)


def test_cached_cash_closing_cannot_post_a_second_shortage(client, db_session):
    login_admin(client)
    actor_id = uuid.UUID(client.get("/api/auth/me").json()["id"])
    company, cash, difference, _contributions, _funding = treasury_setup(client)
    response = client.post("/api/treasury/cash-closings", json={
        "treasuryAccountId": cash["id"], "closingDate": "2026-01-31",
        "openingAmount": "1000.00", "expectedAmount": "1000.00", "countedAmount": "980.00",
    })
    assert response.status_code == 201, response.text
    closing_id = uuid.UUID(response.json()["id"])
    with SessionLocal() as stale:
        cached = stale.get(CashClosing, closing_id)
        assert cached.status == "DRAFT"
        approved = client.post(
            f"/api/treasury/cash-closings/{closing_id}/approve?companyId={company['id']}",
            json={"differenceAccountId": difference["id"]},
        )
        assert approved.status_code == 200, approved.text
        assert cached.status == "DRAFT"
        with pytest.raises(InvalidInvoiceStateError):
            treasury_service.approve_cash_closing(
                stale, cash_closing_id=closing_id, approved_by_user_id=actor_id,
                difference_account_id=uuid.UUID(difference["id"]), company_id=uuid.UUID(company["id"]),
            )
        stale.rollback()
    with SessionLocal() as check:
        documents = list(check.scalars(select(AccountingDocument).where(
            AccountingDocument.company_id == uuid.UUID(company["id"]),
            AccountingDocument.document_type_code == "CCL",
        )))
        assert len(documents) == 1
        closing = check.get(CashClosing, closing_id)
        assert str(closing.accounting_document_id) == approved.json()["accountingDocumentId"]
    account = next(row for row in client.get(f"/api/treasury/accounts?companyId={company['id']}").json() if row["id"] == cash["id"])
    assert Decimal(account["balance"]) == Decimal("980.00")
