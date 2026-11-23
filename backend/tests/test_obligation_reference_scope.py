"""Payment references are scoped to a plan, not globally across plans.

Only synthetic QA records; external tracking does not post to the ledger.
"""
from datetime import timedelta
from decimal import Decimal

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_same_external_reference_is_valid_for_distinct_plans(client):
    login_admin(client)
    company = create_company(client, name="QA plan-scoped receipt references")
    due = business_today() + timedelta(days=5)
    ids = []
    for title in ("QA independent plan alpha", "QA independent plan beta"):
        created = client.post("/api/obligation-plans", json={
            "companyId": company["id"],
            "title": title,
            "category": "GENERAL",
            "scope": "PERSONAL",
            "currencyCode": "HNL",
            "amount": "100.00",
            "recurrence": "ONCE",
            "firstDueDate": due.isoformat(),
            "dueDay": due.day,
        })
        assert created.status_code == 201, created.text
        ids.append(created.json()["id"])

    for plan_id in ids:
        recorded = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
            "occurrenceDueDate": due.isoformat(),
            "paymentDate": business_today().isoformat(),
            "amount": "20.00",
            "reference": "QA-SHARED-EXTERNAL-REF",
        })
        assert recorded.status_code == 201, recorded.text
        assert recorded.json()["accountingStatus"] == "UNPOSTED_MANUAL"

    for plan_id in ids:
        receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
        assert receipts.status_code == 200, receipts.text
        assert len(receipts.json()) == 1
        assert Decimal(receipts.json()[0]["amount"]) == Decimal("20.00")

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line.get("planId") in ids]
    assert len(lines) == 2
    assert {line["planId"] for line in lines} == set(ids)
    assert all(Decimal(line["remaining"]) == Decimal("80.00") for line in lines)
