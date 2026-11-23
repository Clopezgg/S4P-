"""Cancellation retains previously recorded off-ledger receipts and rejects new ones.

Synthetic QA only; no bank or general-ledger postings.
"""
from datetime import timedelta
from decimal import Decimal

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_cancelled_plan_keeps_receipt_and_rejects_later_payment(client):
    login_admin(client)
    company = create_company(client, name="QA cancelled receipt retention")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA cancelled plan history",
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
    payment = {
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": "QA-CANCEL-HISTORY-001",
    }
    first = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payment)
    assert first.status_code == 201, first.text
    receipt_id = first.json()["id"]

    cancelled = client.patch(f"/api/obligation-plans/{plan_id}/status?status=CANCELLED")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"

    rejected = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **payment, "reference": "QA-CANCEL-HISTORY-002",
    })
    assert rejected.status_code == 409, rejected.text

    history = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert history.status_code == 200, history.text
    assert len(history.json()) == 1
    assert history.json()[0]["id"] == receipt_id
    assert Decimal(history.json()[0]["amount"]) == Decimal("25.00")
    assert history.json()[0]["accountingStatus"] == "UNPOSTED_MANUAL"
