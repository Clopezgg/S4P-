"""Procurement and maintenance needs are not payable amounts."""
from tests.helpers import create_company, login_admin


def test_work_needs_requires_authentication(client):
    result = client.get("/api/work-needs/overview", params={
        "companyId": "00000000-0000-0000-0000-000000000001",
    })
    assert result.status_code == 401


def test_work_needs_empty_company_has_no_estimated_purchases(client):
    login_admin(client)
    company = create_company(client)
    result = client.get("/api/work-needs/overview", params={"companyId": company["id"]})
    assert result.status_code == 200, result.text
    assert result.json() == {"materials": [], "maintenance": []}


def test_work_needs_reads_existing_requisitions_and_maintenance(client, db_session):
    from datetime import date
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy import select

    from app.models.equipment import Equipment, MaintenanceOrder
    from app.models.procurement import PurchaseRequisition, PurchaseRequisitionLine
    from app.models.user import User
    from tests.conftest import BOOTSTRAP_ADMIN_EMAIL

    login_admin(client)
    company = create_company(client)
    user = db_session.execute(
        select(User).where(User.email == BOOTSTRAP_ADMIN_EMAIL)
    ).scalar_one()
    requisition = PurchaseRequisition(
        company_id=UUID(company["id"]), requisition_number="MAT-NEED-1",
        requester_id=user.id, priority="HIGH", status="APPROVED",
        required_date=date(2026, 12, 2),
    )
    db_session.add(requisition)
    db_session.flush()
    db_session.add(PurchaseRequisitionLine(
        purchase_requisition_id=requisition.id, description="Cable 2x12 + tierra",
        quantity=Decimal("3.0000"), estimated_unit_cost=Decimal("50.0000"),
    ))
    vehicle = Equipment(
        company_id=UUID(company["id"]), equipment_type="TRUCK",
        name="Vehículo de prueba", status="UNDER_MAINTENANCE",
    )
    db_session.add(vehicle)
    db_session.flush()
    db_session.add(MaintenanceOrder(
        equipment_id=vehicle.id, order_type="CORRECTIVE", status="OPEN",
        opened_at=date(2026, 11, 20), parts_cost=Decimal("150.00"),
        labor_cost=Decimal("75.00"), description="Revisión eléctrica",
    ))
    db_session.commit()

    response = client.get("/api/work-needs/overview", params={"companyId": company["id"]})
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["materials"]) == 1
    assert data["materials"][0]["description"] == "Cable 2x12 + tierra"
    assert Decimal(data["materials"][0]["estimatedTotal"]) == Decimal("150.00000000")
    assert data["maintenance"][0]["equipmentName"] == "Vehículo de prueba"
    assert data["maintenance"][0]["recordedPartsCost"] == "150.00"
    assert data["maintenance"][0]["recordedLaborCost"] == "75.00"
