"""Add private off-ledger recurring obligation tracking (expand-only).

Revision ID: 742fbe13c921
Revises: 9083ca4ebf44
Create Date: 2026-11-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "742fbe13c921"
down_revision = "9083ca4ebf44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "obligation_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("payee", sa.String(200), nullable=True),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("recurrence", sa.String(16), nullable=False),
        sa.Column("first_due_date", sa.Date(), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("last_due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.CheckConstraint("amount > 0", name="ck_obligation_plans_amount"),
        sa.CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_obligation_plans_due_day"),
        sa.CheckConstraint("recurrence IN ('ONCE','MONTHLY')", name="ck_obligation_plans_recurrence"),
        sa.CheckConstraint("scope IN ('PERSONAL','BUSINESS','THIRD_PARTY')", name="ck_obligation_plans_scope"),
        sa.CheckConstraint("category IN ('LAND','CONTRACTOR','MATERIAL','VEHICLE','GENERAL','OTHER')", name="ck_obligation_plans_category"),
        sa.CheckConstraint("status IN ('ACTIVE','PAUSED','CANCELLED')", name="ck_obligation_plans_status"),
    )
    op.create_index("ix_obligation_plans_company_id", "obligation_plans", ["company_id"])
    op.create_index("ix_obligation_plans_owner_user_id", "obligation_plans", ["owner_user_id"])
    op.create_table(
        "obligation_settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("obligation_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("occurrence_due_date", sa.Date(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference", sa.String(160), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_obligation_settlements_amount"),
        sa.UniqueConstraint("plan_id", "reference", name="uq_obligation_settlements_reference"),
    )
    op.create_index("ix_obligation_settlements_plan_id", "obligation_settlements", ["plan_id"])


def downgrade() -> None:
    # Preserve user-entered financial evidence on code rollback.
    # Do not destructively drop business tables.
    pass
