"""Regression: commitment overview must not leak private plans across owners.

Synthetic QA data only; no ledger posting or production writes.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, create_user_with_role, login_admin, login_as


def test_private_plan_hidden_from_other_admin_in_company_overview(client, db_session):
    login_admin(client)
    company = create_company(client, name="QA private overview isolation")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA owner-only commitment",
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

    owner_view = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert owner_view.status_code == 200, owner_view.text
    assert any(line.get("planId") == plan_id for line in owner_view.json()["lines"])

    create_user_with_role(
        db_session,
        email="private-overview-isolation@nexora.group",
        role_name="Administrator",
    )
    login_as(client, email="private-overview-isolation@nexora.group")
    other_view = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert other_view.status_code == 200, other_view.text
    assert all(line.get("planId") != plan_id for line in other_view.json()["lines"])

    login_admin(client)
    restored = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert restored.status_code == 200, restored.text
    assert any(line.get("planId") == plan_id for line in restored.json()["lines"])
