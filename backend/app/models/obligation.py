"""Recurring personal/project commitments, separate from the ERP general ledger.

ObligationSettlement is an external-payment evidence record, not a bank movement.
The owner must have access to the referenced company but records remain private
to their creator, including when scope=BUSINESS or THIRD_PARTY.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ObligationPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "obligation_plans"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_obligation_plans_amount"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_obligation_plans_due_day"),
        CheckConstraint("recurrence IN ('ONCE','MONTHLY')", name="ck_obligation_plans_recurrence"),
        CheckConstraint("scope IN ('PERSONAL','BUSINESS','THIRD_PARTY')", name="ck_obligation_plans_scope"),
        CheckConstraint("category IN ('LAND','CONTRACTOR','MATERIAL','VEHICLE','GENERAL','OTHER')", name="ck_obligation_plans_category"),
        CheckConstraint("status IN ('ACTIVE','PAUSED','CANCELLED')", name="ck_obligation_plans_status"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payee: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    recurrence: Mapped[str] = mapped_column(String(16), nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_day: Mapped[int] = mapped_column(nullable=False)
    last_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")


class ObligationSettlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only off-ledger payment evidence, without accounting side-effects."""
    __tablename__ = "obligation_settlements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_obligation_settlements_amount"),
        UniqueConstraint("plan_id", "reference", name="uq_obligation_settlements_reference"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("obligation_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    occurrence_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
