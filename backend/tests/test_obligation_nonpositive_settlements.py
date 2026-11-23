"""Reject non-positive external settlement amounts without financial side effects.

Uses an isolated QA company and synthetic amounts; never posts to GL.
"""
from datetime import timedelta

import pytest

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


@pytest.mark.parametrize("invalid_amount", ["0.00", "-0.01"])
def test_nonpositive_external_settlement_does_not_create_receipt(client, invalid_amount):
    login_admin(client)
    company = create_company(client, name="QA nonpositive settlement")
    due = business_today() + timedelta(days=7)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA nonpositive settlement",
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
        "amount": invalid_amount,
        "reference": "QA-NONPOSITIVE",
    })
    assert rejected.status_code == 422, rejected.text
    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert receipts.json() == []
    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    line = next(item for item in overview.json()["lines"] if item["planId"] == plan_id)
    assert str(line["remaining"]) in ("125.00", "125.0", "125")
    assert str(line["paid"]) in ("0.00", "0.0", "0")
