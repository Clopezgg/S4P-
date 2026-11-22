"""Safety regressions for the read-only commitments center."""
from tests.helpers import create_company, login_admin


def test_commitments_requires_authentication(client):
    response = client.get("/api/commitments/overview", params={
        "companyId": "00000000-0000-0000-0000-000000000001",
    })
    assert response.status_code == 401


def test_commitments_rejects_missing_or_invalid_company_id(client):
    """Never silently fall back to another company when the scope is invalid."""
    login_admin(client)
    for params in ({}, {"companyId": "not-a-uuid"}, {"companyId": ""}):
        response = client.get("/api/commitments/overview", params=params)
        assert response.status_code == 422, response.text


def test_commitments_empty_company_never_invents_upcoming_payments(client):
    login_admin(client)
    company = create_company(client)
    response = client.get(
        "/api/commitments/overview",
        params={"companyId": company["id"], "horizon_days": 90},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lines"] == []
    assert data["pendingByCurrency"] == {}
    assert data["overdueByCurrency"] == {}
    assert data["pendingByScope"] == {}
    assert data["overdueByScope"] == {}


def test_commitments_rejects_unbounded_forecast(client):
    login_admin(client)
    company = create_company(client)
    response = client.get(
        "/api/commitments/overview",
        params={"companyId": company["id"], "horizon_days": 99999},
    )
    assert response.status_code == 422


def test_commitments_rejects_zero_and_negative_forecast(client):
    """A nonpositive horizon must not silently produce misleading obligations."""
    login_admin(client)
    company = create_company(client)
    for horizon in (0, -1):
        response = client.get(
            "/api/commitments/overview",
            params={"companyId": company["id"], "horizon_days": horizon},
        )
        assert response.status_code == 422, response.text


def test_commitments_accepts_maximum_forecast_without_inventing_data(client):
    """The documented 365-day limit is inclusive and remains read-only."""
    login_admin(client)
    company = create_company(client)
    response = client.get(
        "/api/commitments/overview",
        params={"companyId": company["id"], "horizon_days": 365},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lines"] == []
    assert data["pendingByCurrency"] == {}
    assert data["overdueByCurrency"] == {}


def test_commitments_rejects_forecast_just_above_limit(client):
    """Reject the first invalid day, not only obviously huge horizons."""
    login_admin(client)
    company = create_company(client)
    response = client.get(
        "/api/commitments/overview",
        params={"companyId": company["id"], "horizon_days": 366},
    )
    assert response.status_code == 422, response.text


def test_commitment_status_prioritizes_remaining_and_due_date():
    """A partially paid overdue debt must not appear as merely partially paid."""
    from datetime import date
    from decimal import Decimal

    from app.api.routes.commitments import _status

    today = date(2026, 11, 22)
    assert _status(today, Decimal("0"), Decimal("100"), today) == "DUE"
    assert _status(today, Decimal("20"), Decimal("80"), today) == "DUE"
    assert _status(date(2026, 11, 21), Decimal("20"), Decimal("80"), today) == "OVERDUE"
    assert _status(date(2026, 11, 23), Decimal("20"), Decimal("80"), today) == "PARTIALLY_PAID"
    assert _status(date(2026, 11, 23), Decimal("0"), Decimal("100"), today) == "UPCOMING"
    assert _status(date(2026, 11, 21), Decimal("100"), Decimal("0"), today) == "PAID"


def test_commitment_reminders_fire_only_on_documented_days():
    """Do not emit early or repeated reminders on other future dates."""
    from datetime import date, timedelta

    from app.api.routes.commitments import _alert_due

    today = date(2026, 11, 22)
    for days in (-30, -1, 0, 1, 3, 7):
        assert _alert_due(today + timedelta(days=days), today), days
    for days in (2, 4, 5, 6, 8, 30):
        assert not _alert_due(today + timedelta(days=days), today), days


def test_commitments_rejects_non_numeric_forecast(client):
    """Malformed horizon inputs must not silently select a default forecast."""
    login_admin(client)
    company = create_company(client)
    for horizon in ("abc", "1.5", ""):
        response = client.get(
            "/api/commitments/overview",
            params={"companyId": company["id"], "horizon_days": horizon},
        )
        assert response.status_code == 422, response.text


def test_commitments_accepts_minimum_forecast_without_inventing_data(client):
    """The one-day lower boundary remains valid and cannot create phantom debt."""
    login_admin(client)
    company = create_company(client)
    response = client.get(
        "/api/commitments/overview",
        params={"companyId": company["id"], "horizon_days": 1},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lines"] == []
    assert data["pendingByCurrency"] == {}
    assert data["overdueByCurrency"] == {}
    assert data["pendingByScope"] == {}
    assert data["overdueByScope"] == {}


def test_commitment_alerts_handle_leap_day_and_year_rollover():
    """Reminder offsets must use actual calendar days across month/year boundaries."""
    from datetime import date

    from app.api.routes.commitments import _alert_due

    # 2028 is a leap year: Feb 29 is exactly one day after Feb 28.
    assert _alert_due(date(2028, 2, 29), date(2028, 2, 28))
    assert _alert_due(date(2028, 3, 3), date(2028, 2, 29))
    assert not _alert_due(date(2028, 3, 2), date(2028, 2, 29))
    # Year-end boundaries must not accidentally suppress the 3-day reminder.
    assert _alert_due(date(2027, 1, 2), date(2026, 12, 30))
    assert not _alert_due(date(2027, 1, 3), date(2026, 12, 30))


def test_commitments_repeated_reads_are_stable_for_empty_company(client):
    """Refreshing the dashboard must not materialize planned payments or balances."""
    login_admin(client)
    company = create_company(client)
    params = {"companyId": company["id"], "horizon_days": 30}
    first = client.get("/api/commitments/overview", params=params)
    second = client.get("/api/commitments/overview", params=params)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["lines"] == []
    for field in ("pendingByCurrency", "overdueByCurrency", "pendingByScope", "overdueByScope"):
        assert first.json()[field] == {}


def test_commitments_isolate_private_plans_by_company(client):
    """A private plan in one company must not leak into another company's dashboard."""
    from datetime import timedelta

    from app.core.business_time import business_today

    login_admin(client)
    first_company = create_company(client, name="Isolation A")
    second_company = create_company(client, name="Isolation B")
    due = business_today() + timedelta(days=7)
    created = client.post("/api/obligation-plans", json={
        "companyId": first_company["id"],
        "title": "Isolation test commitment",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "125.00",
        "recurrence": "ONCE",
        "firstDueDate": due.isoformat(),
        "dueDay": due.day,
    })
    assert created.status_code == 201, created.text
    first = client.get("/api/commitments/overview", params={
        "companyId": first_company["id"], "horizon_days": 30,
    })
    second = client.get("/api/commitments/overview", params={
        "companyId": second_company["id"], "horizon_days": 30,
    })
    assert first.status_code == second.status_code == 200
    assert any(line["planId"] == created.json()["id"] for line in first.json()["lines"])
    assert second.json()["lines"] == []
    assert second.json()["pendingByCurrency"] == {}
    assert second.json()["pendingByScope"] == {}


def test_private_plan_list_is_scoped_to_requested_company(client):
    """The plans API must not reveal a private plan from a different company."""
    from datetime import timedelta

    from app.core.business_time import business_today

    login_admin(client)
    company_a = create_company(client, name="Private list A")
    company_b = create_company(client, name="Private list B")
    due = business_today() + timedelta(days=7)
    created = client.post("/api/obligation-plans", json={
        "companyId": company_a["id"],
        "title": "Company A private plan",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "125.00",
        "recurrence": "ONCE",
        "firstDueDate": due.isoformat(),
        "dueDay": due.day,
    })
    assert created.status_code == 201, created.text
    own = client.get("/api/obligation-plans", params={"companyId": company_a["id"]})
    other = client.get("/api/obligation-plans", params={"companyId": company_b["id"]})
    assert own.status_code == other.status_code == 200
    assert any(plan["id"] == created.json()["id"] for plan in own.json())
    assert other.json() == []


def test_external_settlement_rejects_duplicate_reference_without_double_counting(client):
    """An external receipt reference is idempotency protection, not a GL posting."""
    from datetime import timedelta

    from app.core.business_time import business_today

    login_admin(client)
    company = create_company(client, name="Settlement duplicate guard")
    due = business_today() + timedelta(days=7)
    created = client.post("/api/obligation-plans", json={
        "companyId": company["id"],
        "title": "External settlement regression",
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
    payload = {
        "occurrenceDueDate": due.isoformat(),
        "paymentDate": business_today().isoformat(),
        "amount": "25.00",
        "reference": "TEST-EXTERNAL-RECEIPT-001",
    }
    first = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["accountingStatus"] == "UNPOSTED_MANUAL"
    repeated = client.post(f"/api/obligation-plans/{plan_id}/settlements", json=payload)
    assert repeated.status_code == 409, repeated.text
    receipts = client.get(f"/api/obligation-plans/{plan_id}/settlements")
    assert receipts.status_code == 200, receipts.text
    assert len(receipts.json()) == 1
    assert receipts.json()[0]["id"] == first.json()["id"]
    overview = client.get("/api/commitments/overview", params={
        "companyId": company["id"], "horizon_days": 30,
    })
    assert overview.status_code == 200, overview.text
    line = next(line for line in overview.json()["lines"] if line["planId"] == plan_id)
    assert float(line["paid"]) == 25.0
    assert float(line["remaining"]) == 100.0
