"""Authentication regressions for private commitment endpoints.

All requests are unauthenticated; no production data or external services are used.
"""
import uuid

import pytest


@pytest.mark.parametrize("authorization", [
    None,
    "Bearer invalid-qa-token",
    "Basic Zm9vOmJhcg==",
    "Bearer",
])
def test_private_obligation_routes_require_authentication(client, authorization):
    """Neither missing nor invalid credentials may expose private obligations."""
    unknown_plan = str(uuid.uuid4())
    company = str(uuid.uuid4())
    plan = {
        "companyId": company,
        "title": "Unauthenticated QA plan",
        "category": "GENERAL",
        "scope": "PERSONAL",
        "currencyCode": "HNL",
        "amount": "10.00",
        "recurrence": "ONCE",
        "firstDueDate": "2027-01-15",
        "dueDay": 15,
    }
    settlement = {
        "occurrenceDueDate": "2027-01-15",
        "paymentDate": "2026-11-22",
        "amount": "1.00",
        "reference": "QA-NO-AUTH",
    }
    cases = [
        ("get", "/api/commitments/overview", {"params": {"companyId": company}}),
        ("get", "/api/obligation-plans", {"params": {"companyId": company}}),
        ("post", "/api/obligation-plans", {"json": plan}),
        ("get", f"/api/obligation-plans/{unknown_plan}/settlements", {}),
        ("post", f"/api/obligation-plans/{unknown_plan}/settlements", {"json": settlement}),
        ("patch", f"/api/obligation-plans/{unknown_plan}/status", {"params": {"status": "PAUSED"}}),
    ]
    headers = {"Authorization": authorization} if authorization else {}
    for method, path, kwargs in cases:
        response = getattr(client, method)(path, headers=headers, **kwargs)
        assert response.status_code == 401, (method, path, response.text)
