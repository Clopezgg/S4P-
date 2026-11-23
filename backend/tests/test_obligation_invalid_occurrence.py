"""An external receipt must reference an actual installment of its plan.

Synthetic QA fixtures only; no general-ledger or production writes.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_external_receipt_rejects_nonexistent_installment_without_mutation(client):
    login_admin(client)
    company = create_company(client, name="QA nonexistent installment")
    due = business_today() + timedelta(days=7)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA one-time installment",
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

    # A one-time obligation cannot accept a receipt against a second date.
    rejected = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        "occurrenceDueDate": (due + timedelta(days=1)).isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": "QA-NONEXISTENT-INSTALLMENT",
    })
    assert rejected.status_code == 422, rejected.text

    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert receipts.json() == []

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line["planId"] == plan_id]
    assert len(lines) == 1
    assert float(lines[0]["paid"]) == 0.0
    assert float(lines[0]["remaining"]) == 125.0
