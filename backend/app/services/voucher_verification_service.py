"""Verificación pública de comprobantes (orden maestra correctiva §39-§42).

El PDF incluye un QR que codifica `<PUBLIC_BASE>/verificar/comprobante/<token>`.
`token` es aleatorio opaco (secrets), persistido por AccountingDocument. El
endpoint público resuelve el token a un conjunto MÍNIMO de datos —
nunca cuenta bancaria completa, evidencia, IDs técnicos, blob keys ni secretos.
"""

import secrets
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.accounting import AccountingDocument
from app.models.voucher_issuance import VoucherIssuance
from app.models.voucher_verification import VoucherVerification


def get_or_create_token(
    db: Session,
    *,
    accounting_document_id: uuid.UUID,
    document_number: str,
    company_name: str,
    beneficiary: str,
    approved_by: str | None,
    issued_on: date,
    amount: Decimal,
    currency_code: str,
    document_status: str,
    verification_code: str,
) -> str:
    row = db.execute(
        select(VoucherVerification).where(
            VoucherVerification.accounting_document_id == accounting_document_id
        )
    ).scalar_one_or_none()

    if row is None:
        row = VoucherVerification(
            accounting_document_id=accounting_document_id,
            token=secrets.token_urlsafe(24),
            document_number=document_number,
            company_name=company_name,
            beneficiary=beneficiary,
            approved_by=approved_by,
            issued_on=issued_on,
            amount=amount,
            currency_code=currency_code,
            document_status=document_status,
            verification_code=verification_code,
        )
        db.add(row)
        db.flush()
    # Reprinting never rewrites the original public identity. Accounting
    # status is resolved live by verify(), without requiring a new PDF.

    return row.token


def verify(db: Session, *, token: str) -> dict | None:
    result = db.execute(
        select(VoucherVerification, AccountingDocument.status, VoucherIssuance)
        .join(AccountingDocument, AccountingDocument.id == VoucherVerification.accounting_document_id)
        .outerjoin(VoucherIssuance, VoucherIssuance.accounting_document_id == AccountingDocument.id)
        .where(VoucherVerification.token == token)
    ).one_or_none()
    if result is None:
        return None
    row, document_status, issuance = result
    # Issuance is authoritative even when an older application version
    # overwrote the token metadata on reprint.
    return {
        "verified": True,
        "documentNumber": issuance.document_number if issuance else row.document_number,
        "company": issuance.company_name_snapshot if issuance else row.company_name,
        "beneficiary": issuance.beneficiary_name_snapshot if issuance else row.beneficiary,
        "issuedOn": (issuance.issued_on if issuance else row.issued_on).isoformat(),
        "amount": str(issuance.amount_snapshot if issuance else row.amount),
        "currency": issuance.currency_code_snapshot if issuance else row.currency_code,
        "status": document_status,
        "verificationCode": issuance.verification_code if issuance else row.verification_code,
    }
