"""Regression: rejected overpayment cannot mutate a partially settled obligation.

Synthetic QA data only; settlements remain external/unposted.
"""
from datetime import timedelta
from decimal import Decimal

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_overpayment_after_partial_settlement_preserves_balance_and_receipt(client):
    login_admin(client)
    company = create_company(client, name="QA partial overpayment atomicity")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA partial overpayment",
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
        "amount": "40.00",
        "reference": "QA-PARTIAL-001",
    }
    accepted = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payment)
    assert accepted.status_code == 201, accepted.text
    receipt_id = accepted.json()["id"]

    rejected = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **payment, "amount": "60.01", "reference": "QA-OVERPAY-001",
    })
    assert rejected.status_code == 422, rejected.text

    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert len(receipts.json()) == 1
    assert receipts.json()[0]["id"] == receipt_id
    assert Decimal(receipts.json()[0]["amount"]) == Decimal("40.00")
    assert receipts.json()[0]["accountingStatus"] == "UNPOSTED_MANUAL"

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line["planId"] == plan_id]
    assert len(lines) == 1
    assert Decimal(lines[0]["paid"]) == Decimal("40.00")
    assert Decimal(lines[0]["remaining"]) == Decimal("60.00")
