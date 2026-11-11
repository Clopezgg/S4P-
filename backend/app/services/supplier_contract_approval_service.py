"""Supplier-contract review through the existing approval inbox, one transaction."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_correlation_id
from app.domain.errors import (
    InvalidApprovalStateError,
    InvalidFinancialReferenceError,
    NotAuthorizedError,
    NotFoundError,
    SegregationOfDutiesError,
)
from app.models.supplier import (
    SUPPLIER_STATUSES_BLOCKING_NEW,
    Supplier,
    SupplierContract,
)
from app.models.user import User
from app.services import approval_service, audit_service
from app.services.permission_service import (
    assert_company_access,
    assert_project_access,
    user_has_permission,
)


def _authorize(db, *, user_id, contract, resource, action):
    if not user_has_permission(db, user_id=user_id, resource=resource, action=action):
        raise NotAuthorizedError("El usuario no tiene permiso para esta acción contractual")
    assert_company_access(db, user_id=user_id, resource=resource, action=action, company_id=contract.company_id)
    if contract.project_id is not None:
        assert_project_access(db, user_id=user_id, resource=resource, action=action, project_id=contract.project_id)


def _locked(db, contract_id):
    contract = db.scalar(select(SupplierContract).where(SupplierContract.id == contract_id).with_for_update().execution_options(populate_existing=True))
    if contract is None:
        raise NotFoundError("Contrato no encontrado")
    return contract


def submit(db: Session, *, contract_id: uuid.UUID, requested_by: uuid.UUID,
           assigned_to: uuid.UUID) -> SupplierContract:
    contract = _locked(db, contract_id)
    _authorize(db, user_id=requested_by, contract=contract, resource="procurement.contract", action="create")
    if contract.status not in {"DRAFT", "REJECTED"}:
        raise InvalidApprovalStateError("Solo un contrato borrador o rechazado puede enviarse a revisión")
    if requested_by == assigned_to:
        raise SegregationOfDutiesError("Solicitante y aprobador del contrato deben ser distintos")
    approver = db.get(User, assigned_to)
    if approver is None or not approver.is_active:
        raise InvalidFinancialReferenceError("El aprobador debe ser un usuario activo")
    _authorize(db, user_id=assigned_to, contract=contract, resource="workflow.approval", action="decide")
    supplier = db.get(Supplier, contract.supplier_id)
    if supplier is None or supplier.status in SUPPLIER_STATUSES_BLOCKING_NEW:
        raise InvalidFinancialReferenceError("El proveedor no está disponible para aprobar contratos")
    before = contract.status
    contract.status = "REVIEW"
    approval_service.create_request(db, policy_id=None, entity_type="procurement.contract",
        entity_id=contract.id, company_id=contract.company_id, project_id=contract.project_id,
        requested_by=requested_by, assigned_to=assigned_to, module="procurement", amount=contract.value)
    audit_service.record(db, actor_user_id=requested_by, action="procurement.contract.submit",
        entity_type="procurement.contract", entity_id=contract.id, company_id=contract.company_id,
        project_id=contract.project_id, before={"status": before}, after={"status": contract.status},
        correlation_id=get_correlation_id())
    db.flush()
    return contract


def apply_decision(db: Session, contract_id: uuid.UUID, decision: str, decided_by: uuid.UUID) -> None:
    contract = _locked(db, contract_id)
    _authorize(db, user_id=decided_by, contract=contract, resource="workflow.approval", action="decide")
    if contract.status != "REVIEW" or decision not in {"APPROVED", "REJECTED"}:
        raise InvalidApprovalStateError("El contrato no tiene una revisión pendiente válida")
    if decision == "APPROVED":
        supplier = db.get(Supplier, contract.supplier_id)
        if supplier is None or supplier.status in SUPPLIER_STATUSES_BLOCKING_NEW:
            raise InvalidFinancialReferenceError("El proveedor no está disponible para aprobar contratos")
    contract.status = "ACTIVE" if decision == "APPROVED" else "REJECTED"
    audit_service.record(db, actor_user_id=decided_by, action="procurement.contract.decide",
        entity_type="procurement.contract", entity_id=contract.id, company_id=contract.company_id,
        project_id=contract.project_id, before={"status": "REVIEW"}, after={"status": contract.status},
        correlation_id=get_correlation_id())
    db.flush()


def assert_not_under_review_or_rejected(db: Session, contract_id: uuid.UUID | None) -> None:
    """Retain legacy DRAFT compatibility; a submitted/rejected contract is blocked."""
    if contract_id is None:
        return
    contract = db.scalar(select(SupplierContract).where(SupplierContract.id == contract_id).with_for_update().execution_options(populate_existing=True))
    if contract is not None and contract.status in {"REVIEW", "REJECTED"}:
        raise InvalidApprovalStateError("El contrato requiere aprobación antes de crear obligaciones o pagos")


def assert_financial_approval(db: Session, contract_id: uuid.UUID | None) -> None:
    """Obligations may be prepared; posting or paying requires real approval."""
    if contract_id is None:
        return
    contract = _locked(db, contract_id)
    if contract.status != "ACTIVE":
        raise InvalidApprovalStateError("El contrato debe estar aprobado y activo antes de contabilizar o pagar")
