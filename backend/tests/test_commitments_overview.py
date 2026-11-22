"""Safety regressions for the read-only commitments center."""
from tests.helpers import create_company, login_admin


def test_commitments_requires_authentication(client):
    response = client.get("/api/commitments/overview", params={
        "companyId": "00000000-0000-0000-0000-000000000001",
    })
    assert response.status_code == 401


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
