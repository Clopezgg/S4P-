"""widen customer invoice lifecycle status

Revision ID: 7b2c1af4849c
Revises: eb8ce8e18b2d
Create Date: 2026-11-09 00:06:23.962850

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7b2c1af4849c'
down_revision: Union[str, None] = 'eb8ce8e18b2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'customer_invoices', 'status', existing_type=sa.String(16),
        type_=sa.String(32), existing_nullable=False,
    )


def downgrade() -> None:
    # Application rollback may keep the wider column. Never truncate a real
    # PARTIALLY_COLLECTED state merely to undo a schema migration.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM customer_invoices WHERE length(status) > 16) THEN
                RAISE EXCEPTION 'Cannot narrow invoice status while long lifecycle states exist';
            END IF;
        END $$;
    """)
    op.alter_column(
        'customer_invoices', 'status', existing_type=sa.String(32),
        type_=sa.String(16), existing_nullable=False,
    )
