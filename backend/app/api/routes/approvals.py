import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_correlation import get_correlation_id
from app.models.supplier import Supplier, SupplierContract
from app.models.user import User
from app.repositories import approval_repository
from app.schemas.approval import ApprovalRequestResponse
from app.services import approval_service, audit_service
from app.services.permission_service import (
    accessible_project_ids,
    assert_company_access,
    require_permission,
)

"""Approval Inbox API (Track G / Platform, NXR-REQ-0088). Generic across
domains -- ver docs/superpowers/specs/2026-08-25-track-g-workflow-audit-design.md.
`GET` lista lo asignado al usuario autenticado; `POST /decide` aplica
Segregación de Funciones (`approval_service.decide`) y registra el propio
AuditLog de la ApprovalRequest (antes/después de su status)."""

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    # Literal whitelist at the schema layer (HTTP callers get a clean 422
    # straight from Pydantic); approval_service.decide() ALSO validates
    # this independently (app/services/approval_service.py::APPROVAL_DECISIONS)
    # since decide() is a service entry point other code calls directly,
    # not only this route -- don't rely on the schema layer alone.
    decision: Literal["APPROVED", "REJECTED"]
    comment: str | None = None


def _approval_response(db, row):
    response = ApprovalRequestResponse.model_validate(row, from_attributes=True)
    requester = db.get(User, row.requested_by)
    response.requested_by_name = requester.full_name if requester else None
    if row.entity_type == "procurement.contract":
        contract = db.get(SupplierContract, row.entity_id)
        if contract is not None and contract.company_id == row.company_id:
            supplier = db.get(Supplier, contract.supplier_id)
            response.entity_label = f"Contrato {contract.contract_number}" + (f" · {supplier.legal_name}" if supplier else "")
            response.currency_code = contract.currency_code
    return response


@router.get("", response_model=list[ApprovalRequestResponse])
def list_my_approvals(
    company_id: uuid.UUID = Query(alias="companyId"),
    module: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(require_permission("workflow.approval", "read")),
) -> list[ApprovalRequestResponse]:
    assert_company_access(
        db, user_id=user.id, resource="workflow.approval", action="read", company_id=company_id
    )
    rows = approval_repository.list_assigned_to(
        db, user_id=user.id, company_id=company_id, module=module
    )
    allowed = accessible_project_ids(db, user_id=user.id, resource="workflow.approval", action="read")
    if allowed is not None:
        rows = [row for row in rows if row.project_id is None or row.project_id in allowed]
    return [_approval_response(db, r) for r in rows]


@router.post("/{request_id}/decide", response_model=ApprovalRequestResponse)
def decide_approval(
    request_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    user=Depends(require_permission("workflow.approval", "decide")),
    correlation_id: str = Depends(get_correlation_id),
) -> ApprovalRequestResponse:
    try:
        existing = approval_repository.get_for_update(db, request_id=request_id)
        assert_company_access(
            db,
            user_id=user.id,
            resource="workflow.approval",
            action="decide",
            company_id=existing.company_id,
        )
        before_status = existing.status
        updated = approval_service.decide(
            db,
            request_id=request_id,
            decided_by=user.id,
            decision=body.decision,
            comment=body.comment,
        )
        audit_service.record(
            db,
            actor_user_id=user.id,
            action="workflow.approval.decide",
            entity_type="workflow.approval_request",
            entity_id=updated.id,
            company_id=updated.company_id,
            project_id=updated.project_id,
            before={"status": before_status},
            after={"status": updated.status},
            correlation_id=correlation_id,
        )
        db.commit()
        return _approval_response(db, updated)
    except Exception:
        db.rollback()
        raise
