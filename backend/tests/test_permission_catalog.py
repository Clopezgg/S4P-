"""A routed permission absent from the catalog makes an action unreachable."""
import ast
from pathlib import Path

from app.repositories.permission_repository import _BASE_PERMISSIONS


def test_all_literal_route_permissions_exist_in_seeded_catalog():
    catalog = {(resource, action) for resource, action, _ in _BASE_PERMISSIONS}
    missing = []
    for path in (Path(__file__).resolve().parents[1] / 'app/api/routes').glob('*.py'):
        for call in ast.walk(ast.parse(path.read_text())):
            if not isinstance(call, ast.Call) or ast.unparse(call.func) != 'require_permission':
                continue
            if len(call.args) < 2 or not all(isinstance(v, ast.Constant) for v in call.args[:2]):
                continue
            permission = tuple(v.value for v in call.args[:2])
            if permission not in catalog:
                missing.append((path.name, call.lineno, permission))
    assert missing == [], f'Unreachable backend actions: {missing}'


def test_bootstrap_revokes_legacy_auditor_schedule_write_grant(client, db_session):
    from sqlalchemy import select

    from app.models.permission import SCOPE_ANY, Permission, RolePermission
    from app.models.role import Role
    from app.repositories.permission_repository import ensure_base_permissions

    auditor = db_session.scalar(select(Role).where(Role.name == "Auditor"))
    permission = db_session.scalar(select(Permission).where(
        Permission.resource == "contract.payment_schedule", Permission.action == "manage"))
    legacy = RolePermission(role_id=auditor.id, permission_id=permission.id, company_scope=SCOPE_ANY)
    db_session.add(legacy)
    db_session.commit()
    ensure_base_permissions(db_session)
    db_session.commit()
    ensure_base_permissions(db_session)
    assert db_session.scalar(select(RolePermission.id).where(
        RolePermission.role_id == auditor.id, RolePermission.permission_id == permission.id)) is None
    for name in ("Administrator", "Procurement Manager"):
        assert db_session.scalar(select(RolePermission.id).join(Role).where(
            Role.name == name, RolePermission.permission_id == permission.id)) is not None
