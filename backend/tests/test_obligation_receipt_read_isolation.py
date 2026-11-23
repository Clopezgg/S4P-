"""Regression: a different administrator cannot read an existing private receipt.

Synthetic QA data only. No ledger posting or production changes.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, create_user_with_role, login_admin, login_as


def test_private_settlement_receipt_hidden_from_another_administrator(client, db_session):
    login_admin(client)
    company = create_company(client, name="QA receipt privacy boundary")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA confidential receipt",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "100.00",
        "recurrence": "ONCE",
        "firstDueDate": due.isoformat(),
        "dueDay": due.day,
    })
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]

    paid = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": "QA-PRIVATE-RECEIPT-READ",
    })
    assert paid.status_code == 201, paid.text
    assert paid.json()["accountingStatus"] == "UNPOSTED_MANUAL"

    create_user_with_role(
        db_session,
        email="receipt-reader-isolation@nexora.group",
        role_name="Administrator",
    )
    login_as(client, email="receipt-reader-isolation@nexora.group")
    forbidden = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert forbidden.status_code == 404, forbidden.text

    login_admin(client)
    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert len(receipts.json()) == 1
    assert receipts.json()[0]["reference"] == "QA-PRIVATE-RECEIPT-READ"
