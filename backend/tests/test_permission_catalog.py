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
