"""Partial external payments accumulate without exceeding an installment.

Synthetic QA data only; the off-ledger tracker never creates GL entries.
"""
from datetime import timedelta
from decimal import Decimal

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_partial_payments_accumulate_and_rejected_overage_is_atomic(client):
    login_admin(client)
    company = create_company(client, name="QA partial settlement atomicity")
    due = business_today() + timedelta(days=4)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA partial settlement",
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
    base = {
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
    }

    for amount, reference in (("30.00", "QA-PARTIAL-A"), ("25.00", "QA-PARTIAL-B")):
        result = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
            **base, "amount": amount, "reference": reference,
        })
        assert result.status_code == 201, result.text
        assert result.json()["accountingStatus"] == "UNPOSTED_MANUAL"

    rejected = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **base, "amount": "45.01", "reference": "QA-PARTIAL-OVERAGE",
    })
    assert rejected.status_code == 422, rejected.text

    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert len(receipts.json()) == 2
    assert {item["reference"] for item in receipts.json()} == {
        "QA-PARTIAL-A", "QA-PARTIAL-B",
    }
    assert sum(Decimal(item["amount"]) for item in receipts.json()) == Decimal("55.00")

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line["planId"] == plan_id]
    assert len(lines) == 1
    assert Decimal(lines[0]["paid"]) == Decimal("55.00")
    assert Decimal(lines[0]["remaining"]) == Decimal("45.00")
