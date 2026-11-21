"""Recurring obligations: calendar, isolation intent, non-posting partial payments."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.obligation_schedule_service import due_in_month, occurrence_dates
from tests.helpers import create_company, login_admin


def test_thirtieth_clamps_february_and_first_date_stays_exact():
    plan = SimpleNamespace(
        first_due_date=date(2026, 12, 30), last_due_date=None,
        due_day=30, recurrence="MONTHLY", status="ACTIVE",
    )
    assert occurrence_dates(plan, date(2027, 3, 31)) == [
        date(2026, 12, 30), date(2027, 1, 30),
        date(2027, 2, 28), date(2027, 3, 30),
    ]
    assert due_in_month(2028, 2, 31) == date(2028, 2, 29)


def test_private_plan_payment_tracking_without_gl_posting(client):
    login_admin(client)
    company = create_company(client)
    response = client.post("/api/obligation-plans", json={
        "companyId": company["id"], "title": "Cuota terreno de prueba",
        "payee": "Vendedor", "category": "LAND", "scope": "PERSONAL",
        "currencyCode": "HNL", "amount": "1000.00",
        "recurrence": "MONTHLY", "firstDueDate": "2026-12-30", "dueDay": 30,
    })
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["amount"] == "1000.00"

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 365,
    })
    assert overview.status_code == 200, overview.text
    rows = [line for line in overview.json()["lines"] if line["source"] == "MANUAL"]
    assert any(line["dueDate"] == "2027-02-28" for line in rows)

    payment = {
        "occurrenceDueDate": "2026-12-30", "paymentDate": "2026-11-01",
        "amount": "400.00", "reference": "RECIBO-UNICO-TEST",
    }
    paid = client.post(f"/api/obligation-plans/{plan['id']}/settlements", json=payment)
    assert paid.status_code == 201, paid.text
    assert paid.json()["accountingStatus"] == "UNPOSTED_MANUAL"

    future = client.post(f"/api/obligation-plans/{plan['id']}/settlements", json={
        **payment, "reference": "FUTURO-TEST", "paymentDate": "2030-01-01",
    })
    assert future.status_code == 422

    again = client.post(f"/api/obligation-plans/{plan['id']}/settlements", json=payment)
    assert again.status_code == 409
    excess = client.post(f"/api/obligation-plans/{plan['id']}/settlements", json={
        **payment, "amount": "601.00", "reference": "RECIBO-EXCESO",
    })
    assert excess.status_code == 422

    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 365,
    }).json()
    december = next(line for line in overview["lines"] if line["dueDate"] == "2026-12-30")
    assert Decimal(december["remaining"]) == Decimal("600.00")
    assert Decimal(december["paid"]) == Decimal("400.00")

    pause = client.patch(f"/api/obligation-plans/{plan['id']}/status?status=PAUSED")
    assert pause.status_code == 200, pause.text
    remaining = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 365,
    }).json()
    assert not [line for line in remaining["lines"] if line["source"] == "MANUAL"]
