"""Official PDF contract against authenticated API, real GL and PostgreSQL."""
import re
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.models.accounting import AccountingDocument, JournalLine
from app.models.voucher_issuance import VoucherIssuance
from app.models.voucher_verification import VoucherVerification
from tests.helpers import create_company, login_admin
from tests.test_company_branding_voucher import _outflow


def test_official_cash_voucher_has_two_letter_pages_and_verifiable_gl_link(client, db_session):
    login_admin(client)
    company = create_company(client, name="S4P isolated PDF QA")
    document_id = uuid.UUID(_outflow(client, company["id"]))
    profile = client.patch(
        f"/api/master-data/companies/{company['id']}",
        json={"voucherApproverName": "QA Approver"},
    )
    assert profile.status_code == 200, profile.text
    url = f"/api/treasury/vouchers/{document_id}?beneficiary=QA%20Supplier&paymentMethod=Efectivo"
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert "S4P-Comprobante-" in response.headers["content-disposition"]
    pdf = response.content
    assert pdf.startswith(b"%PDF-")
    # Match page dictionaries, excluding the /Pages tree dictionary.
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 2
    boxes = re.findall(rb"/MediaBox\s*\[\s*([^]]+)\]", pdf)
    assert len(boxes) == 2
    assert all([Decimal(x.decode()) for x in box.split()] == [0, 0, 612, 792] for box in boxes)
    assert b"S4P" in pdf
    assert b"COMPROBANTE DE PAGO" in pdf
    assert b"/verificar/comprobante/" in pdf
    assert str(document_id).encode() not in pdf

    document = db_session.get(AccountingDocument, document_id)
    assert document.company_id == uuid.UUID(company["id"])
    lines = list(db_session.scalars(select(JournalLine).where(JournalLine.accounting_document_id == document_id)))
    assert sum((line.debit_amount for line in lines), Decimal(0)) == Decimal("100.00")
    assert sum((line.credit_amount for line in lines), Decimal(0)) == Decimal("100.00")
    issuance = db_session.scalar(select(VoucherIssuance).where(VoucherIssuance.accounting_document_id == document_id))
    token = db_session.scalar(select(VoucherVerification).where(VoucherVerification.accounting_document_id == document_id))
    assert issuance is not None and token is not None
    assert f"/verificar/comprobante/{token.token}".encode() in pdf
    assert client.get(url).status_code == 200
    assert len(list(db_session.scalars(select(VoucherIssuance).where(VoucherIssuance.accounting_document_id == document_id)))) == 1

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get(url).status_code == 401
    verification = client.get(f"/api/verificar/comprobante/{token.token}")
    assert verification.status_code == 200, verification.text
    assert verification.json()["verified"] is True
    assert verification.json()["documentNumber"] == document.document_number
    assert str(document_id) not in verification.text
