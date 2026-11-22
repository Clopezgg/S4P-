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
