"""A logged-out user cannot read or modify private payment receipts.

Synthetic QA records only; no accounting posting or production changes.
"""
from datetime import timedelta

from app.core.business_time import business_today
from tests.helpers import create_company, login_admin


def test_logout_blocks_receipt_reads_and_writes_without_changing_balance(client):
    login_admin(client)
    company = create_company(client, name="QA logout receipt boundary")
    due = business_today() + timedelta(days=5)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA protected external receipt",
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
    assert client.post("/api/auth/logout").status_code == 204

    payload = {
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": "QA-LOGGED-OUT-REJECTED",
    }
    denied_write = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payload)
    denied_read = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert denied_write.status_code == 401, denied_write.text
    assert denied_read.status_code == 401, denied_read.text

    login_admin(client)
    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert receipts.json() == []
    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    lines = [line for line in overview.json()["lines"] if line.get("planId") == plan_id]
    assert len(lines) == 1
    assert lines[0]["remaining"] == "100.00"
