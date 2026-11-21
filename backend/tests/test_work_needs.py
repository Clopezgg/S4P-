"""Procurement and maintenance needs are not payable amounts."""
from tests.helpers import create_company, login_admin


def test_work_needs_requires_authentication(client):
    result = client.get("/api/work-needs/overview", params={
        "companyId": "00000000-0000-0000-0000-000000000001",
    })
    assert result.status_code == 401


def test_work_needs_empty_company_has_no_estimated_purchases(client):
    login_admin(client)
    company = create_company(client)
    result = client.get("/api/work-needs/overview", params={"companyId": company["id"]})
    assert result.status_code == 200, result.text
    assert result.json() == {"materials": [], "maintenance": []}
