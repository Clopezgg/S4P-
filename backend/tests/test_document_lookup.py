"""Centro de Control por Número de Documento (§31/§32) + action policy (§33)."""

from tests.helpers import create_account, create_company, create_supplier, login_admin


def test_lookup_finds_supplier_invoice_and_contract_by_number_with_actions(client, db_session):
    login_admin(client)
    company = create_company(client)
    supplier = create_supplier(client, company_id=company["id"], legal_name="Contratista X")
    contract = client.post(
        "/api/procurement/suppliers/contracts",
        json={
            "companyId": company["id"], "supplierId": supplier["id"],
            "contractNumber": "10101960", "value": "1500000.00", "currencyCode": "HNL",
            "startDate": "2026-08-01",
        },
    ).json()
    expense = create_account(client, company_id=company["id"], code="5100", name="Obra", account_type="EXPENSE")
    payable = create_account(client, company_id=company["id"], code="2100", name="CxP", account_type="LIABILITY")
    invoice = client.post(
        "/api/ap/supplier-invoices",
        json={
            "companyId": company["id"], "supplierId": supplier["id"], "invoiceNumber": "2020485218",
            "scope": "GENERAL", "expenseAccountId": expense["id"], "payableAccountId": payable["id"],
            "currencyCode": "HNL", "amount": "50000.00", "invoiceDate": "2026-08-22", "dueDate": "2026-09-02",
            "supplierContractId": contract["id"],
        },
    ).json()

    # Búsqueda exacta por número de factura.
    r = client.get("/api/accounting/documents/lookup?q=2020485218")
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    inv_hit = next(h for h in results if h["entityType"] == "SUPPLIER_INVOICE")
    assert inv_hit["id"] == invoice["id"]
    assert inv_hit["exact"] is True
    assert inv_hit["party"] == "Contratista X"
    assert inv_hit["number"] == "2020485218"
    # DRAFT permite editar / enviar / aprobar / cancelar, no un DELETE universal.
    assert "edit" in inv_hit["allowedActions"]
    assert "delete" not in inv_hit["allowedActions"]

    # Búsqueda por número de contrato.
    c = client.get("/api/accounting/documents/lookup?q=10101960")
    contract_hit = next(h for h in c.json()["results"] if h["entityType"] == "SUPPLIER_CONTRACT")
    assert contract_hit["id"] == contract["id"]
    assert contract_hit["amount"] == "1500000.00"
    assert "activate" in contract_hit["allowedActions"]


def test_lookup_exact_match_ranks_first(client, db_session):
    login_admin(client)
    company = create_company(client)
    supplier = create_supplier(client, company_id=company["id"])
    expense = create_account(client, company_id=company["id"], code="5100", name="Obra", account_type="EXPENSE")
    payable = create_account(client, company_id=company["id"], code="2100", name="CxP", account_type="LIABILITY")
    for number in ("F-100", "F-1000", "F-10001"):
        client.post("/api/ap/supplier-invoices", json={
            "companyId": company["id"], "supplierId": supplier["id"], "invoiceNumber": number,
            "scope": "GENERAL", "expenseAccountId": expense["id"], "payableAccountId": payable["id"],
            "currencyCode": "HNL", "amount": "10.00", "invoiceDate": "2026-08-01", "dueDate": "2026-09-01",
        })
    r = client.get("/api/accounting/documents/lookup?q=F-100")
    results = r.json()["results"]
    assert results[0]["number"] == "F-100"
    assert results[0]["exact"] is True


def test_lookup_requires_auth(client):
    assert client.get("/api/accounting/documents/lookup?q=x").status_code in (401, 403)


def test_lookup_does_not_expose_general_journal_with_unassigned_project_lines(client, db_session):
    import uuid

    from app.models.permission import UserCompanyAccess, UserProjectAccess
    from tests.helpers import create_user_with_role, login_as

    login_admin(client)
    company = create_company(client)
    projects = []
    for code in ['VISIBLE', 'PRIVATE']:
        response = client.post('/api/projects', json={'companyId': company['id'],
            'name': code, 'code': code, 'currencyCode': 'HNL'})
        assert response.status_code == 201, response.text
        projects.append(response.json())
    expense = create_account(client, company_id=company['id'], code='5100', name='Cost', account_type='EXPENSE')
    payable = create_account(client, company_id=company['id'], code='2100', name='AP', account_type='LIABILITY')
    posted = client.post('/api/accounting/journal-entries', json={
        'companyId': company['id'], 'scope': 'GENERAL', 'currencyCode': 'HNL',
        'lines': [{'accountId': expense['id'], 'debitAmount': '100', 'projectId': projects[1]['id']},
                  {'accountId': payable['id'], 'creditAmount': '100', 'projectId': projects[1]['id']}]})
    assert posted.status_code == 201, posted.text
    supplier = create_supplier(client, company_id=company['id'])
    visible_contract = None
    for index in range(27):
        response = client.post('/api/procurement/suppliers/contracts', json={
            'companyId': company['id'], 'supplierId': supplier['id'],
            'projectId': projects[0 if index == 26 else 1]['id'],
            'contractNumber': f'LIMIT-{index}', 'value': '10',
            'currencyCode': 'HNL', 'startDate': '2026-01-01'})
        assert response.status_code == 201, response.text
        if index == 26:
            visible_contract = response.json()
    user = create_user_with_role(db_session, email='lookup-lines@example.com', role_name='Finance Manager')
    db_session.add(UserCompanyAccess(user_id=user.id, company_id=uuid.UUID(company['id'])))
    db_session.add(UserProjectAccess(user_id=user.id, project_id=uuid.UUID(projects[0]['id'])))
    db_session.commit()
    login_as(client, email=user.email)
    document = posted.json()
    assert client.get(f"/api/accounting/journal-entries/{document['id']}").status_code == 403
    result = client.get('/api/accounting/documents/lookup', params={'q': document['documentNumber']})
    assert result.status_code == 200, result.text
    assert result.json()['results'] == []
    limited = client.get('/api/accounting/documents/lookup', params={'q': 'LIMIT-'})
    assert limited.status_code == 200, limited.text
    assert [row['id'] for row in limited.json()['results']] == [visible_contract['id']]
