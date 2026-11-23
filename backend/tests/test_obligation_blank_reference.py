"""Whitespace-only payment references must not create off-ledger receipts.

Uses isolated QA fixtures; does not mutate bank accounts or the general ledger.
"""
from datetime import timedelta

import pytest

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


@pytest.mark.parametrize("reference", ["   ", "  X  ", "\t\t\t"])
def test_external_settlement_rejects_blank_or_short_trimmed_reference(client, reference):
    login_admin(client)
    company = create_company(client, name="QA invalid receipt reference")
    due = business_today() + timedelta(days=4)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA receipt reference validation",
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

    rejected = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": reference,
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
