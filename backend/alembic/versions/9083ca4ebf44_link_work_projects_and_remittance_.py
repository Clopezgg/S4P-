"""link work projects and remittance attribution

Revision ID: 9083ca4ebf44
Revises: 32c92271c634
Create Date: 2026-11-13 09:34:46.203148

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9083ca4ebf44'
down_revision: Union[str, None] = '32c92271c634'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A downgrade retains additive business fields. Re-upgrade must accept
    # that exact retained schema instead of deleting attribution history.
    bind = op.get_bind()
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS parent_project_id uuid")
    op.execute("ALTER TABLE remittances ADD COLUMN IF NOT EXISTS attributed_project_id uuid")
    if not any(c['name'] == 'uq_projects_id_company' for c in sa.inspect(bind).get_unique_constraints('projects')):
        op.create_unique_constraint('uq_projects_id_company', 'projects', ['id', 'company_id'])
    if not any(c['name'] == 'fk_projects_parent_company' for c in sa.inspect(bind).get_foreign_keys('projects')):
        op.create_foreign_key('fk_projects_parent_company', 'projects', 'projects', ['parent_project_id', 'company_id'], ['id', 'company_id'], ondelete='RESTRICT')
    if not any(c['name'] == 'ck_projects_not_own_parent' for c in sa.inspect(bind).get_check_constraints('projects')):
        op.create_check_constraint('ck_projects_not_own_parent', 'projects', 'parent_project_id IS NULL OR parent_project_id <> id')
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_parent_project_id ON projects (parent_project_id)")
    if not any(c['name'] == 'fk_remittances_project_company' for c in sa.inspect(bind).get_foreign_keys('remittances')):
        op.create_foreign_key('fk_remittances_project_company', 'remittances', 'projects', ['attributed_project_id', 'company_id'], ['id', 'company_id'], ondelete='RESTRICT')
    op.execute("CREATE INDEX IF NOT EXISTS ix_remittances_attributed_project_id ON remittances (attributed_project_id)")


def downgrade() -> None:
    # Expand-only rollback: previous code ignores these nullable columns.
    # Retain project hierarchy and attribution history; never erase user links.
    pass
