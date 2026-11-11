from app.repositories import role_repository, user_repository
from app.security.passwords import hash_password
from tests.conftest import BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD


def login_admin(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": BOOTSTRAP_ADMIN_EMAIL, "password": BOOTSTRAP_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_user_with_role(db_session, *, email: str, role_name: str, password: str = "Passw0rd!23"):
    role = role_repository.get_by_name(db_session, role_name)
    assert role is not None, f"role {role_name} no existe (ejecuta ensure_base_roles)"
    user = user_repository.create_user(
        db_session,
        email=email,
        full_name="Usuario de prueba",
        password_hash=hash_password(password),
    )
    role_repository.assign_role(db_session, user_id=user.id, role_id=role.id)
    db_session.commit()
    return user


def login_as(client, *, email: str, password: str = "Passw0rd!23") -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def create_company(client, *, name: str = "Constructora Nexora", currency: str = "HNL") -> dict:
    response = client.post(
        "/api/master-data/companies",
        json={"name": name, "functionalCurrencyCode": currency},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_account(client, *, company_id: str, code: str, name: str, account_type: str) -> dict:
    response = client.post(
        "/api/master-data/accounts",
        json={"companyId": company_id, "code": code, "name": name, "accountType": account_type},
    )
    assert response.status_code == 201, response.text
    return response.json()


def configure_resource_posting(client, *, company_id: str, source_type: str) -> dict:
    expense = create_account(
        client,
        company_id=company_id,
        code={"FUEL": "5110", "MAINTENANCE": "5120", "LABOR": "5130"}[source_type],
        name=f"Costo de {source_type}",
        account_type="EXPENSE",
    )
    offset = create_account(
        client,
        company_id=company_id,
        code="2190",
        name="Recursos por pagar",
        account_type="LIABILITY",
    )
    response = client.put(
        f"/api/master-data/companies/{company_id}/resource-posting-configs/{source_type}",
        json={
            "sourceType": source_type,
            "expenseAccountId": expense["id"],
            "offsetAccountId": offset["id"],
            "active": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_supplier(client, *, company_id: str, legal_name: str = "Proveedor de prueba") -> dict:
    response = client.post(
        "/api/procurement/suppliers",
        json={"companyId": company_id, "legalName": legal_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_customer(client, *, company_id: str, legal_name: str = "Cliente de prueba") -> dict:
    response = client.post(
        "/api/crm/customers",
        json={"companyId": company_id, "legalName": legal_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_treasury_account(
    client, *, company_id: str, gl_account_id: str, name: str = "Banco Principal", kind: str = "BANK"
) -> dict:
    response = client.post(
        "/api/treasury/accounts",
        json={
            "companyId": company_id,
            "name": name,
            "kind": kind,
            "currencyCode": "HNL",
            "glAccountId": gl_account_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def approve_supplier_contract(client, contract: dict) -> dict:
    """Real two-principal approval fixture; never changes status through SQL."""
    import uuid

    import httpx

    saved_cookies = httpx.Cookies(client.cookies)
    approver_email = f"contract-approver-{uuid.uuid4().hex}@example.com"
    password = "Passw0rd!23"
    response = client.post('/api/master-data/users', json={
        'companyId': contract['companyId'], 'email': approver_email,
        'fullName': 'Contract QA approver', 'password': password, 'roleName': 'Administrator'})
    assert response.status_code == 201, response.text
    approver = response.json()
    submitted = client.post(f"/api/procurement/suppliers/contracts/{contract['id']}/submit-for-approval",
                            json={'assignedTo': approver['id']})
    assert submitted.status_code == 200, submitted.text
    logged_in = False
    try:
        login_as(client, email=approver_email, password=password)
        logged_in = True
        response = client.get('/api/approvals', params={'companyId': contract['companyId']})
        assert response.status_code == 200, response.text
        request = next(row for row in response.json() if row['entityId'] == contract['id'])
        decided = client.post(f"/api/approvals/{request['id']}/decide", json={'decision': 'APPROVED'})
        assert decided.status_code == 200, decided.text
        assert decided.json()['decidedBy'] == approver['id']
    finally:
        if logged_in:
            assert client.post('/api/auth/logout').status_code == 204
        client.cookies.clear()
        client.cookies.update(saved_cookies)
    saved = client.get('/api/procurement/suppliers/contracts', params={'company_id': contract['companyId']})
    assert saved.status_code == 200, saved.text
    actual = next(row for row in saved.json() if row['id'] == contract['id'])
    assert actual['status'] == 'ACTIVE'
    return actual
