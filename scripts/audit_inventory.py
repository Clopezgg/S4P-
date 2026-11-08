"""Reproducible static discovery; presence is never runtime verification."""
import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'audit'


def revision(root):
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()


def build():
    functions, endpoints, tables = [], [], []
    for file in sorted((ROOT / 'backend' / 'app').rglob('*.py')):
        source = file.read_text()
        tree = ast.parse(source)
        path = str(file.relative_to(ROOT))
        prefix = ''
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func) == 'APIRouter':
                for kw in node.keywords:
                    if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__tablename__' for t in child.targets):
                        tables.append({'file': path, 'line': node.lineno, 'model': node.name, 'table': ast.literal_eval(child.value), 'definition': ast.get_source_segment(source, node)})
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = sorted({ast.unparse(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)})
            permissions = sorted({ast.unparse(c) for c in ast.walk(node) if isinstance(c, ast.Call) and any(term in ast.unparse(c.func) for term in ('require_permission', 'assert_company_access', 'assert_project_access'))})
            item = {'file': path, 'line': node.lineno, 'function': node.name, 'signature': ast.unparse(node.args), 'purpose': ast.get_docstring(node), 'calls': calls, 'permission_expressions': permissions, 'raises': sorted({ast.unparse(c.exc) for c in ast.walk(node) if isinstance(c, ast.Raise) and c.exc}), 'status': 'PARCIAL', 'evidence_limit': 'Static discovery; per-action UI/API/DB verification pending'}
            functions.append(item)
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in {'get', 'post', 'put', 'patch', 'delete'}:
                    route = ast.literal_eval(dec.args[0]) if dec.args and isinstance(dec.args[0], ast.Constant) else '?'
                    endpoints.append(item | {'method': dec.func.attr.upper(), 'router_path': prefix + route, 'decorator': ast.unparse(dec)})
    frontend = []
    for file in sorted((ROOT / 'frontend' / 'src').rglob('*')):
        if file.suffix not in {'.ts', '.tsx'} or '.test.' in file.name:
            continue
        source = file.read_text()
        frontend.append({'file': str(file.relative_to(ROOT)), 'routes': re.findall(r"['\"](/[^'\"\s]*)['\"]", source), 'imports': re.findall(r"from ['\"]([^'\"]+)['\"]", source), 'ui_action_lines': [{'line': n, 'source': s.strip()} for n, s in enumerate(source.splitlines(), 1) if re.search(r'<(Button|button|form|Form|Input|Select|textarea)|onClick=|onSubmit=|useMutation|useQuery', s)], 'status': 'PARCIAL'})
    manifests = ['frontend/package.json', 'backend/requirements.txt', 'backend/requirements-dev.txt']
    nexora = ROOT.parent / 'nexora-group'
    comparison = []
    for file in sorted((ROOT / 'backend' / 'app').rglob('*.py')):
        other = nexora / file.relative_to(ROOT)
        if not other.exists():
            kind = 'S4P_ONLY'
        elif file.read_bytes() == other.read_bytes():
            kind = 'IDENTICAL'
        elif file.read_text().replace('NEXORA GROUP', 'S4P').replace('NEXORA', 'S4P') == other.read_text().replace('NEXORA GROUP', 'S4P').replace('NEXORA', 'S4P'):
            kind = 'BRAND_ONLY'
        else:
            kind = 'DIFF_REQUIRES_REVIEW'
        comparison.append({'file': str(file.relative_to(ROOT)), 'comparison': kind})
    tracked_files = subprocess.check_output(
        ['git', '-C', str(ROOT), 'ls-files'], text=True,
    ).splitlines()
    data = {'baseline_sha': revision(ROOT), 'nexora_sha': revision(nexora), 'classification': 'Static presence only; no implicit VERIFIED status', 'tracked_files': tracked_files, 'other_entrypoints': [p for p in tracked_files if p.startswith(('scripts/', 'infra/', 'functions/', 'supabase/', 'frontend/public/'))], 'functions': functions, 'endpoints': endpoints, 'models': tables, 'frontend': frontend, 'migrations': [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'backend/alembic/versions').glob('*.py'))], 'tests': [str(p.relative_to(ROOT)) for pattern in ('backend/tests/test_*.py', 'frontend/e2e/*.spec.ts', 'frontend/src/**/*.test.ts*', 'frontend/tests/**/*.test.ts*') for p in sorted(ROOT.glob(pattern))], 'workflows': {str(p.relative_to(ROOT)): p.read_text() for p in sorted((ROOT / '.github/workflows').glob('*.yml'))}, 'dependencies': {p: (ROOT / p).read_text() for p in manifests}, 'backend_comparison': comparison}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'inventory.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    counts = {k: len(data[k]) for k in ('functions', 'endpoints', 'models', 'frontend', 'migrations', 'tests', 'workflows')}
    (OUT / 'inventory-summary.json').write_text(json.dumps(counts, indent=2) + '\n')
    print(json.dumps(counts))


if __name__ == '__main__':
    build()
