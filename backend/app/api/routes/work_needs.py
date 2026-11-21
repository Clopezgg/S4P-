"""Read-only work and procurement needs; none of these are booked cash outflows."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.company import Company
from app.models.equipment import Equipment, MaintenanceOrder
from app.models.procurement import PurchaseRequisition, PurchaseRequisitionLine
from app.schemas.base import CamelModel
from app.services.permission_service import (
    accessible_project_ids,
    assert_company_access,
    user_has_permission,
)

router = APIRouter(prefix="/work-needs", tags=["work-needs"])


class MaterialNeed(CamelModel):
    id: uuid.UUID
    requisition_id: uuid.UUID
    requisition_number: str
    description: str
    quantity: Decimal
    estimated_unit_cost: Decimal
    estimated_total: Decimal
    priority: str
    required_date: date | None
    currency_code: str | None
    status: str
    project_id: uuid.UUID | None


class MaintenanceNeed(CamelModel):
    id: uuid.UUID
    equipment_id: uuid.UUID
    equipment_name: str
    description: str | None
    status: str
    opened_at: date
    recorded_parts_cost: Decimal
    recorded_labor_cost: Decimal
    currency_code: str | None


class WorkNeedsResponse(CamelModel):
    materials: list[MaterialNeed] = Field(default_factory=list)
    maintenance: list[MaintenanceNeed] = Field(default_factory=list)


@router.get("/overview", response_model=WorkNeedsResponse)
def work_needs(
    company_id: uuid.UUID = Query(alias="companyId"),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
) -> WorkNeedsResponse:
    user, _ = current
    assert_company_access(db, user_id=user.id, resource="core.company",
                          action="read", company_id=company_id)
    company = db.get(Company, company_id)
    if company is None:
        return WorkNeedsResponse()
    materials: list[MaterialNeed] = []
    maintenance: list[MaintenanceNeed] = []

    if user_has_permission(
        db, user_id=user.id, resource="procurement.requisition", action="read",
    ):
        allowed = accessible_project_ids(
            db, user_id=user.id, resource="procurement.requisition", action="read",
        )
        stmt = (
            select(PurchaseRequisition, PurchaseRequisitionLine)
            .join(
                PurchaseRequisitionLine,
                PurchaseRequisitionLine.purchase_requisition_id == PurchaseRequisition.id,
            )
            .where(
                PurchaseRequisition.company_id == company_id,
                PurchaseRequisition.status.in_(("DRAFT", "SUBMITTED", "APPROVED")),
            )
            .order_by(PurchaseRequisition.required_date, PurchaseRequisition.id)
        )
        for req, line in db.execute(stmt).all():
            if allowed is not None and req.project_id is not None and req.project_id not in allowed:
                continue
            materials.append(MaterialNeed(
                id=line.id,
                requisition_id=req.id,
                requisition_number=req.requisition_number,
                description=line.description,
                quantity=line.quantity,
                estimated_unit_cost=line.estimated_unit_cost,
                estimated_total=line.quantity * line.estimated_unit_cost,
                priority=req.priority,
                required_date=req.required_date,
                currency_code=company.functional_currency_code,
                status=req.status,
                project_id=req.project_id,
            ))

    if user_has_permission(
        db, user_id=user.id, resource="equipment.maintenance_order", action="read",
    ) and user_has_permission(
        db, user_id=user.id, resource="equipment.equipment", action="read",
    ):
        allowed = accessible_project_ids(
            db, user_id=user.id, resource="equipment.equipment", action="read",
        )
        stmt = (
            select(MaintenanceOrder, Equipment)
            .join(Equipment, Equipment.id == MaintenanceOrder.equipment_id)
            .where(
                Equipment.company_id == company_id,
                MaintenanceOrder.status.in_(("OPEN", "IN_PROGRESS")),
            )
            .order_by(MaintenanceOrder.opened_at.desc(), MaintenanceOrder.id)
        )
        for order, asset in db.execute(stmt).all():
            if allowed is not None and asset.project_id is not None and asset.project_id not in allowed:
                continue
            maintenance.append(MaintenanceNeed(
                id=order.id, equipment_id=asset.id,
                equipment_name=asset.name,
                description=order.description,
                status=order.status, opened_at=order.opened_at,
                recorded_parts_cost=order.parts_cost,
                recorded_labor_cost=order.labor_cost,
                currency_code=company.functional_currency_code,
            ))
    return WorkNeedsResponse(materials=materials, maintenance=maintenance)
