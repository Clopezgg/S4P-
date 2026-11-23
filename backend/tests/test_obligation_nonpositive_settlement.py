"""Reject non-positive external settlements without changing receipt history.

Uses a synthetic company and plan; never posts bank or GL transactions.
"""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


@pytest.mark.parametrize("invalid_amount", ["0", "0.00", "-0.01", "-100.00"])
def test_non_positive_external_payment_is_rejected_atomically(client, invalid_amount):
    login_admin(client)
    company = create_company(client, name="QA nonpositive settlement validation")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA invalid external settlement",
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

    response = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": invalid_amount,
        "reference": "QA-INVALID-NONPOSITIVE-001",
    })
    assert response.status_code == 422, response.text

    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert receipts.json() == []

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line["planId"] == plan_id]
    assert len(lines) == 1
    assert Decimal(lines[0]["paid"]) == Decimal("0.00")
    assert Decimal(lines[0]["remaining"]) == Decimal("100.00")
