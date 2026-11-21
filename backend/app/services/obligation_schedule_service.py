"""Canonical monthly schedule and off-ledger balances, without bank/GL effects."""
import calendar
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.obligation import ObligationPlan, ObligationSettlement


def due_in_month(year: int, month: int, day: int) -> date:
    if not 1 <= day <= 31:
        raise ValueError("El día de vencimiento debe estar entre 1 y 31")
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def occurrence_dates(plan: ObligationPlan, until: date) -> list[date]:
    first = plan.first_due_date
    if first > until or plan.status == "CANCELLED":
        return []
    if plan.recurrence == "ONCE":
        return [first] if plan.last_due_date is None or first <= plan.last_due_date else []
    dates = [first]
    year, month = first.year, first.month
    for _ in range(600):
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        due = due_in_month(year, month, plan.due_day)
        if due > until or (plan.last_due_date and due > plan.last_due_date):
            break
        dates.append(due)
    return dates


def sum_paid(db: Session, plan_id: UUID) -> dict[date, Decimal]:
    rows = db.execute(select(ObligationSettlement).where(
        ObligationSettlement.plan_id == plan_id
    )).scalars().all()
    result: dict[date, Decimal] = {}
    for row in rows:
        result[row.occurrence_due_date] = result.get(
            row.occurrence_due_date, Decimal("0")
        ) + row.amount
    return result


def pending_lines(db: Session, *, company_id: UUID, user_id: UUID,
                  today: date, horizon_days: int = 90) -> list[dict]:
    until = today + timedelta(days=horizon_days)
    plans = db.execute(select(ObligationPlan).where(
        ObligationPlan.company_id == company_id,
        ObligationPlan.owner_user_id == user_id,
        ObligationPlan.status == "ACTIVE",
    )).scalars().all()
    lines: list[dict] = []
    for plan in plans:
        paid = sum_paid(db, plan.id)
        for due in occurrence_dates(plan, until):
            applied = paid.get(due, Decimal("0"))
            remaining = max(plan.amount - applied, Decimal("0"))
            if remaining <= 0:
                continue
            status = (
                "OVERDUE" if due < today
                else "DUE" if due == today
                else "PARTIALLY_PAID" if applied > 0
                else "UPCOMING"
            )
            lines.append({
                "id": f"manual:{plan.id}:{due.isoformat()}",
                "source": "MANUAL",
                "title": plan.title,
                "payee": plan.payee,
                "category": plan.category,
                "scope": plan.scope,
                "currency_code": plan.currency_code,
                "due_date": due,
                "amount": plan.amount,
                "paid": applied,
                "remaining": remaining,
                "status": status,
                "detail_url": "/inicio/compromisos",
                "plan_id": plan.id,
                "accounting_status": "UNPOSTED_MANUAL",
            })
    return lines
