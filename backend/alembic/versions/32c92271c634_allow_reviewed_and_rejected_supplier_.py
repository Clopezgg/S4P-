"""allow reviewed and rejected supplier contracts

Revision ID: 32c92271c634
Revises: dae6224cb8be
Create Date: 2026-11-11 06:03:25.464678

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '32c92271c634'
down_revision: Union[str, None] = 'dae6224cb8be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('ck_supplier_contracts_status_valid', 'supplier_contracts', type_='check')
    op.create_check_constraint('ck_supplier_contracts_status_valid', 'supplier_contracts',
        "status IN ('DRAFT','REVIEW','REJECTED','ACTIVE','COMPLETED','TERMINATED')")


def downgrade() -> None:
    # Retain expanded statuses when rolling back the application. Never
    # rewrite pending/rejected contract history to fit the old application.
    pass
