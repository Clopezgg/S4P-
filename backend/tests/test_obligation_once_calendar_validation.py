"""Validation regression for single-installment obligation calendar consistency."""
from tests.helpers import create_company, login_admin


def test_once_plan_rejects_due_day_inconsistent_with_first_date(client):
    login_admin(client)
    company = create_company(client)
    payload = {
        "companyId": company["id"],
        "title": "Single installment calendar QA",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "100.00",
        "recurrence": "ONCE",
        "firstDueDate": "2027-01-15",
        "dueDay": 30,
    }
    rejected = client.post("/api/obligation-plans", json=payload)
    assert rejected.status_code == 422, rejected.text
    listed = client.get("/api/obligation-plans", params={"companyId": company["id"]})
    assert listed.status_code == 200, listed.text
    assert listed.json() == []

    payload["dueDay"] = 15
    accepted = client.post("/api/obligation-plans", json=payload)
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["firstDueDate"] == "2027-01-15"
    assert accepted.json()["dueDay"] == 15
