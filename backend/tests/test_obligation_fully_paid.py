"""Fully settled installments reject further payments without creating receipts.

Uses synthetic QA records; external tracking never posts to the general ledger.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_fully_paid_installment_cannot_be_paid_twice(client):
    login_admin(client)
    company = create_company(client, name="QA fully settled installment")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA fully settled once",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "125.00",
        "recurrence": "ONCE",
        "firstDueDate": due.isoformat(),
        "dueDay": due.day,
    })
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]
    payment = {
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "125.00",
        "reference": "QA-FULL-SETTLEMENT",
    }
    paid = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payment)
    assert paid.status_code == 201, paid.text
    assert paid.json()["accountingStatus"] == "UNPOSTED_MANUAL"

    rejected = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **payment, "amount": "0.01", "reference": "QA-EXTRA-AFTER-FULL",
    })
    assert rejected.status_code == 422, rejected.text

    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert len(receipts.json()) == 1

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line["planId"] == plan_id]
    # The commitments overview is a pending-only projection: fully settled
    # installments are intentionally absent, while their receipts remain
    # available from the settlement history endpoint above.
    assert lines == []
