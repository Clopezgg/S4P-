"""Owner-private recurring obligations. External settlements are NOT ledger postings."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.deps_correlation import get_correlation_id
from app.models.currency import Currency
from app.models.obligation import ObligationPlan, ObligationSettlement
from app.schemas.base import CamelModel
from app.services import audit_service, obligation_schedule_service as schedule
from app.services.permission_service import assert_company_access

router = APIRouter(prefix="/obligation-plans", tags=["obligation-plans"])


class PlanCreate(CamelModel):
    company_id: uuid.UUID
    title: str = Field(min_length=2, max_length=200)
    payee: str | None = Field(default=None, max_length=200)
    category: str
    scope: str
    currency_code: str = Field(min_length=3, max_length=3)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    recurrence: str
    first_due_date: date
    due_day: int = Field(ge=1, le=31)
    last_due_date: date | None = None

    @field_validator("category")
    @classmethod
    def category_valid(cls, value: str) -> str:
        if value not in ("LAND", "CONTRACTOR", "MATERIAL", "VEHICLE", "GENERAL", "OTHER"):
            raise ValueError("Categoría inválida")
        return value

    @field_validator("scope")
    @classmethod
    def scope_valid(cls, value: str) -> str:
        if value not in ("PERSONAL", "BUSINESS", "THIRD_PARTY"):
            raise ValueError("Ámbito inválido")
        return value

    @field_validator("recurrence")
    @classmethod
    def recurrence_valid(cls, value: str) -> str:
        if value not in ("ONCE", "MONTHLY"):
            raise ValueError("Periodicidad inválida")
        return value

    @field_validator("currency_code")
    @classmethod
    def currency_upper(cls, value: str) -> str:
        return value.upper()


class PlanResponse(CamelModel):
    id: uuid.UUID
    title: str
    payee: str | None
    category: str
    scope: str
    currency_code: str
    amount: Decimal
    recurrence: str
    first_due_date: date
    due_day: int
    last_due_date: date | None
    status: str


class SettlementCreate(CamelModel):
    occurrence_due_date: date
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reference: str = Field(min_length=3, max_length=160)


class SettlementResponse(CamelModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    occurrence_due_date: date
    payment_date: date
    amount: Decimal
    reference: str
    accounting_status: str = "UNPOSTED_MANUAL"


def _owner(db: Session, plan_id: uuid.UUID, user_id: uuid.UUID) -> ObligationPlan:
    plan = db.get(ObligationPlan, plan_id)
    if plan is None or plan.owner_user_id != user_id:
        raise HTTPException(404, "Compromiso no encontrado")
    return plan


@router.get("", response_model=list[PlanResponse])
def list_plans(
    company_id: uuid.UUID = Query(alias="companyId"),
    db: Session = Depends(get_db), current=Depends(get_current_user),
):
    user, _ = current
    assert_company_access(
        db, user_id=user.id, resource="core.company", action="read", company_id=company_id
    )
    return db.execute(select(ObligationPlan).where(
        ObligationPlan.company_id == company_id,
        ObligationPlan.owner_user_id == user.id,
    ).order_by(ObligationPlan.created_at.desc())).scalars().all()


@router.post("", response_model=PlanResponse, status_code=201)
def create_plan(
    payload: PlanCreate, db: Session = Depends(get_db),
    current=Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    user, _ = current
    assert_company_access(
        db, user_id=user.id, resource="core.company", action="read",
        company_id=payload.company_id
    )
    if db.get(Currency, payload.currency_code) is None:
        raise HTTPException(422, "Moneda no configurada")
    if payload.last_due_date is not None and payload.last_due_date < payload.first_due_date:
        raise HTTPException(422, "La última cuota no puede ser anterior a la primera")
    if payload.recurrence == "MONTHLY":
        expected_first = schedule.due_in_month(
            payload.first_due_date.year, payload.first_due_date.month, payload.due_day
        )
        if expected_first != payload.first_due_date:
            raise HTTPException(422, "La primera fecha no corresponde al día de pago")
    plan = ObligationPlan(**payload.model_dump(), owner_user_id=user.id, status="ACTIVE")
    db.add(plan)
    db.flush()
    audit_service.record(
        db, actor_user_id=user.id, action="obligation.plan.create",
        entity_type="obligation.plan", entity_id=plan.id,
        company_id=plan.company_id, project_id=None, before=None,
        after={"title": plan.title, "scope": plan.scope, "amount": str(plan.amount),
               "recurrence": plan.recurrence}, correlation_id=correlation_id,
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}/settlements", response_model=list[SettlementResponse])
def list_settlements(
    plan_id: uuid.UUID, db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    user, _ = current
    plan = _owner(db, plan_id, user.id)
    assert_company_access(
        db, user_id=user.id, resource="core.company", action="read", company_id=plan.company_id
    )
    return db.execute(select(ObligationSettlement).where(
        ObligationSettlement.plan_id == plan.id,
    ).order_by(ObligationSettlement.payment_date.desc())).scalars().all()


@router.post("/{plan_id}/settlements", response_model=SettlementResponse, status_code=201)
def record_external_settlement(
    plan_id: uuid.UUID, payload: SettlementCreate,
    db: Session = Depends(get_db), current=Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    user, _ = current
    # Lock the plan row to serialize all payments for a particular installment.
    plan = db.execute(select(ObligationPlan).where(
        ObligationPlan.id == plan_id,
        ObligationPlan.owner_user_id == user.id,
    ).with_for_update()).scalar_one_or_none()
    if plan is None:
        raise HTTPException(404, "Compromiso no encontrado")
    assert_company_access(
        db, user_id=user.id, resource="core.company", action="read",
        company_id=plan.company_id
    )
    if plan.status != "ACTIVE":
        raise HTTPException(409, "El compromiso no está activo")
    if payload.occurrence_due_date not in schedule.occurrence_dates(
        plan, payload.occurrence_due_date
    ):
        raise HTTPException(422, "No existe esa cuota en el calendario del compromiso")
    prior = db.execute(select(func.coalesce(func.sum(ObligationSettlement.amount), 0)).where(
        ObligationSettlement.plan_id == plan.id,
        ObligationSettlement.occurrence_due_date == payload.occurrence_due_date,
    )).scalar_one()
    if payload.amount > plan.amount - Decimal(prior):
        raise HTTPException(422, "El importe supera el saldo de la cuota")
    reference = payload.reference.strip()
    if len(reference) < 3:
        raise HTTPException(422, "Introduce una referencia válida")
    if db.execute(select(ObligationSettlement.id).where(
        ObligationSettlement.plan_id == plan.id,
        ObligationSettlement.reference == reference,
    )).first():
        raise HTTPException(409, "Ya existe un pago de seguimiento con esa referencia")
    row = ObligationSettlement(
        plan_id=plan.id, occurrence_due_date=payload.occurrence_due_date,
        payment_date=payload.payment_date, amount=payload.amount,
        reference=reference, created_by_user_id=user.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Referencia de pago duplicada") from error
    audit_service.record(
        db, actor_user_id=user.id, action="obligation.settlement.record",
        entity_type="obligation.settlement", entity_id=row.id,
        company_id=plan.company_id, project_id=None, before=None,
        after={"planId": str(plan.id), "amount": str(row.amount),
               "occurrence": row.occurrence_due_date.isoformat(),
               "offLedger": True}, correlation_id=correlation_id,
    )
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{plan_id}/status", response_model=PlanResponse)
def change_plan_status(
    plan_id: uuid.UUID, status: str = Query(pattern="^(ACTIVE|PAUSED|CANCELLED)$"),
    db: Session = Depends(get_db), current=Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    user, _ = current
    plan = _owner(db, plan_id, user.id)
    assert_company_access(
        db, user_id=user.id, resource="core.company", action="read", company_id=plan.company_id
    )
    if plan.status == "CANCELLED":
        raise HTTPException(409, "Un compromiso cancelado no se puede reactivar")
    old = plan.status
    plan.status = status
    audit_service.record(
        db, actor_user_id=user.id, action="obligation.plan.status",
        entity_type="obligation.plan", entity_id=plan.id,
        company_id=plan.company_id, project_id=None,
        before={"status": old}, after={"status": plan.status},
        correlation_id=correlation_id,
    )
    db.commit()
    db.refresh(plan)
    return plan
