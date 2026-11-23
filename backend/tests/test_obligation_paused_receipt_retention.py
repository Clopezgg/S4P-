"""Paused plans preserve historical off-ledger receipts without accepting new payments.

Uses only synthetic QA data. No GL, bank, or production writes.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_paused_plan_retains_receipt_and_rejects_new_settlement(client):
    login_admin(client)
    company = create_company(client, name="QA paused receipt retention")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA paused historical receipt",
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
    payload = {
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": "QA-PAUSE-HISTORY-001",
    }
    first = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payload)
    assert first.status_code == 201, first.text
    receipt_id = first.json()["id"]

    paused = client.patch(f"/api/obligation-plans/{plan_id}/status?status=PAUSED")
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "PAUSED"

    rejected = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **payload, "reference": "QA-PAUSE-HISTORY-002",
    })
    assert rejected.status_code == 409, rejected.text

    history = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert history.status_code == 200, history.text
    assert len(history.json()) == 1
    assert history.json()[0]["id"] == receipt_id
    assert history.json()[0]["amount"] == "25.00"
    assert history.json()[0]["accountingStatus"] == "UNPOSTED_MANUAL"
