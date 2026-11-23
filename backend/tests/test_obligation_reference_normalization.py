"""Regression: whitespace cannot bypass external settlement reference uniqueness.

All values are isolated QA fixtures; these receipts never post to GL or banks.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_external_receipt_reference_is_trimmed_before_duplicate_check(client):
    login_admin(client)
    company = create_company(client, name="QA normalized payment reference")
    due = business_today() + timedelta(days=5)
    plan = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA reference normalization",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "125.00",
        "recurrence": "ONCE",
        "firstDueDate": due.isoformat(),
        "dueDay": due.day,
    })
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]
    payload = {
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": "QA-REFERENCE-001",
    }
    first = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payload)
    assert first.status_code == 201, first.text

    duplicate = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **payload, "reference": "  QA-REFERENCE-001  ",
    })
    assert duplicate.status_code == 409, duplicate.text

    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert len(receipts.json()) == 1
    assert receipts.json()[0]["reference"] == "QA-REFERENCE-001"

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line["planId"] == plan_id]
    assert len(lines) == 1
    assert float(lines[0]["paid"]) == 25.0
    assert float(lines[0]["remaining"]) == 100.0
