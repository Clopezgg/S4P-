"""A receipt reference is unique per plan, even across monthly installments.

Synthetic QA records only. No GL, bank or production writes.
"""
from decimal import Decimal

from app.core.business_time import business_today
from app.services.obligation_schedule_service import due_in_month
from tests.helpers import create_company, login_admin


def test_monthly_reference_cannot_be_reused_on_another_installment(client):
    login_admin(client)
    company = create_company(client, name="QA cross-installment reference")
    today = business_today()
    year, month = today.year, today.month
    first = due_in_month(year, month, 15)
    if first <= today:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        first = due_in_month(year, month, 15)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    second = due_in_month(next_year, next_month, 15)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "QA monthly reference uniqueness",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "100.00",
        "recurrence": "MONTHLY",
        "firstDueDate": first.isoformat(),
        "dueDay": 15,
    })
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]
    payload = {
        "paymentDate": today.isoformat(),
        "amount": "25.00",
        "reference": "QA-MONTHLY-REF-001",
    }
    first_payment = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **payload, "occurrenceDueDate": first.isoformat(),
    })
    assert first_payment.status_code == 201, first_payment.text
    duplicate = client.post(f"/api/obligation-plans/{plan_id}/settlements", json={
        **payload, "occurrenceDueDate": second.isoformat(),
    })
    assert duplicate.status_code == 409, duplicate.text
    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert len(receipts.json()) == 1
    assert Decimal(receipts.json()[0]["amount"]) == Decimal("25.00")
    assert receipts.json()[0]["occurrenceDueDate"] == first.isoformat()
