"""Unified read-only due obligations. Each financial source appears once.

No synthetic obligations, no posting, no bank mutations. This view is intentionally
safe to enable before a new durable database and recurring-obligations migration.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.business_time import business_today
from app.models.ap import SupplierInvoice
from app.models.contract_payment import ContractPaymentSchedule
from app.models.supplier import Supplier, SupplierContract
from app.schemas.base import CamelModel
from app.services import contract_payment_service as cps
from app.services import obligation_schedule_service as schedules
from app.services.permission_service import (
    accessible_project_ids,
    assert_company_access,
    user_has_permission,
)

router = APIRouter(prefix="/commitments", tags=["commitments"])


class CommitmentLine(CamelModel):
    id: str
    source: str
    title: str
    payee: str | None = None
    category: str
    currency_code: str
    due_date: date
    amount: Decimal
    paid: Decimal
    remaining: Decimal
    status: str
    detail_url: str
    plan_id: uuid.UUID | None = None
    accounting_status: str = "ERP"
    scope: str = "BUSINESS"
    days_until_due: int = 0
    alert_now: bool = False


class CommitmentsOverview(CamelModel):
    as_of: date
    lines: list[CommitmentLine] = Field(default_factory=list)
    pending_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    overdue_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    pending_by_scope: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    overdue_by_scope: dict[str, dict[str, Decimal]] = Field(default_factory=dict)


def _status(due: date, paid: Decimal, remaining: Decimal, today: date) -> str:
    if remaining <= 0:
        return "PAID"
    if due < today:
        return "OVERDUE"
    if paid > 0:
        return "PARTIALLY_PAID"
    if due == today:
        return "DUE"
    return "UPCOMING"


@router.get("/overview", response_model=CommitmentsOverview)
def overview(
    company_id: uuid.UUID = Query(alias="companyId"),
    horizon_days: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
) -> CommitmentsOverview:
    user, _ = current
    assert_company_access(
        db, user_id=user.id, resource="core.company", action="read", company_id=company_id,
    )
    today = business_today()
    until = today + timedelta(days=horizon_days)
    lines: list[CommitmentLine] = []

    if user_has_permission(db, user_id=user.id, resource="ap.supplier_invoice", action="read"):
        permitted = accessible_project_ids(
            db, user_id=user.id, resource="ap.supplier_invoice", action="read",
        )
        invoices = db.execute(select(SupplierInvoice).where(
            SupplierInvoice.company_id == company_id,
            SupplierInvoice.status.in_(("APPROVED", "SCHEDULED", "PARTIALLY_PAID")),
            SupplierInvoice.due_date <= until,
            # Only invoices with a corresponding visible schedule are de-duplicated below.
        )).scalars().all()
        scheduled_contract_ids: set[uuid.UUID] = set()
        if user_has_permission(
            db, user_id=user.id, resource="contract.payment_schedule", action="read",
        ):
            contract_scope = accessible_project_ids(
                db, user_id=user.id, resource="contract.payment_schedule", action="read",
            )
            visible_schedules = db.execute(select(ContractPaymentSchedule).where(
                ContractPaymentSchedule.company_id == company_id,
                ContractPaymentSchedule.status != "CANCELLED",
            )).scalars().all()
            scheduled_contract_ids = {
                item.supplier_contract_id for item in visible_schedules
                if contract_scope is None or item.project_id is None or item.project_id in contract_scope
            }
        for invoice in invoices:
            if invoice.supplier_contract_id in scheduled_contract_ids:
                continue
            if permitted is not None and invoice.project_id is not None and invoice.project_id not in permitted:
                continue
            total = invoice.amount + invoice.tax_amount
            remaining = max(total - invoice.amount_paid, Decimal("0"))
            if not remaining:
                continue
            supplier = db.get(Supplier, invoice.supplier_id)
            lines.append(CommitmentLine(
                id=f"ap:{invoice.id}", source="AP",
                title=f"Factura {invoice.invoice_number}",
                payee=supplier.legal_name if supplier else None,
                category="PROVEEDOR", currency_code=invoice.currency_code,
                due_date=invoice.due_date, amount=total,
                paid=invoice.amount_paid, remaining=remaining,
                status=_status(invoice.due_date, invoice.amount_paid, remaining, today),
                detail_url="/finanzas/cuentas-por-pagar",
            ))

    if user_has_permission(db, user_id=user.id, resource="contract.payment_schedule", action="read"):
        permitted = accessible_project_ids(
            db, user_id=user.id, resource="contract.payment_schedule", action="read",
        )
        contract_schedules = db.execute(select(ContractPaymentSchedule).where(
            ContractPaymentSchedule.company_id == company_id,
            ContractPaymentSchedule.status != "CANCELLED",
        )).scalars().all()
        for schedule in contract_schedules:
            if permitted is not None and schedule.project_id is not None and schedule.project_id not in permitted:
                continue
            contract = db.get(SupplierContract, schedule.supplier_contract_id)
            for installment in cps.installment_summaries(
                db, schedule_id=schedule.id, as_of=today,
            ):
                if (
                    installment.status == "CANCELLED"
                    or installment.remaining <= 0
                    or installment.due_date > until
                ):
                    continue
                lines.append(CommitmentLine(
                    id=f"contract:{installment.installment_id}",
                    source="CONTRACT",
                    title=f"Contrato {contract.contract_number}" if contract else "Cuota contractual",
                    category="CONTRATISTA",
                    currency_code=schedule.currency_code,
                    due_date=installment.due_date,
                    amount=installment.net_due,
                    paid=installment.paid,
                    remaining=installment.remaining,
                    status=_status(installment.due_date, installment.paid, installment.remaining, today),
                    detail_url="/finanzas/libro-contractual",
                ))

    for item in schedules.pending_lines(
        db, company_id=company_id, user_id=user.id, today=today, horizon_days=horizon_days
    ):
        lines.append(CommitmentLine(**item))

    for item in lines:
        item.days_until_due = (item.due_date - today).days
        # On-screen alert triggers when the user visits the center; no push is implied.
        item.alert_now = item.days_until_due in (7, 3, 1, 0) or item.days_until_due < 0
    lines.sort(key=lambda row: (row.due_date, row.id))
    pending: dict[str, Decimal] = {}
    overdue: dict[str, Decimal] = {}
    pending_by_scope: dict[str, dict[str, Decimal]] = {}
    overdue_by_scope: dict[str, dict[str, Decimal]] = {}
    for item in lines:
        currency = item.currency_code
        pending[currency] = pending.get(currency, Decimal("0")) + item.remaining
        scope_bucket = pending_by_scope.setdefault(item.scope, {})
        scope_bucket[currency] = scope_bucket.get(currency, Decimal("0")) + item.remaining
        if item.due_date < today:
            overdue[currency] = overdue.get(currency, Decimal("0")) + item.remaining
            overdue_bucket = overdue_by_scope.setdefault(item.scope, {})
            overdue_bucket[currency] = overdue_bucket.get(currency, Decimal("0")) + item.remaining
    return CommitmentsOverview(
        as_of=today, lines=lines,
        pending_by_currency=pending, overdue_by_currency=overdue,
        pending_by_scope=pending_by_scope, overdue_by_scope=overdue_by_scope,
    )
