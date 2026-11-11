"""preserve immutable voucher contractual history

Revision ID: dae6224cb8be
Revises: 7b2c1af4849c
Create Date: 2026-11-11 05:24:19.998788

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'dae6224cb8be'
down_revision: Union[str, None] = '7b2c1af4849c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_issuances ADD COLUMN IF NOT EXISTS contract_context_snapshot JSONB")


def downgrade() -> None:
    # Expand-only rollback: retain historical snapshots. Old code ignores
    # the nullable additive column; re-upgrade is idempotent.
    pass
