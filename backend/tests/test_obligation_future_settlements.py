"""Future-dated promises cannot be recorded as completed external payments.

All amounts and company records are synthetic QA fixtures; no GL posting.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_future_dated_external_payment_is_rejected_without_receipt(client):
    login_admin(client)
    company = create_company(client, name="QA future payment guard")
    today = business_today()
    due = today + timedelta(days=7)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA future dated payment",
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
    response = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": (today + timedelta(days=1)).isoformat(),
        "amount": "25.00",
        "reference": "QA-FUTURE-NOT-PAID",
    })
    assert response.status_code == 422, response.text
    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert receipts.json() == []
    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    line = next(row for row in overview.json()["lines"] if row["planId"] == plan_id)
    assert float(line["paid"]) == 0.0
    assert float(line["remaining"]) == 125.0
