"""Upgrade real prior schema and refuse a lossy downgrade with live QA data."""
import os
import shutil
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.main import app
from app.services.bootstrap_service import bootstrap_admin_if_needed
from tests.helpers import create_company, login_admin
from tests.test_financial_audit_atomicity import _invoice

BACKEND = Path(__file__).resolve().parents[1]
DB_NAME = 'nexora_ar_status_migration_s4p'
PREVIOUS = 'eb8ce8e18b2d'


def test_prior_schema_upgrade_preserves_partial_collection_and_blocks_lossy_downgrade(client):
    env = {**os.environ, 'PGHOST': 'localhost', 'PGPORT': '5432', 'PGUSER': 'nexora',
           'PGPASSWORD': os.environ.get('POSTGRES_PASSWORD', 'nexora')}
    url = f"postgresql+psycopg://nexora:{env['PGPASSWORD']}@localhost:5432/{DB_NAME}"
    migration_env = {**env, 'DATABASE_URL': url, 'BOOTSTRAP_ADMIN_EMAIL': '', 'BOOTSTRAP_ADMIN_PASSWORD': ''}

    def migrate(*args):
        return subprocess.run(
            [shutil.which('alembic') or str(BACKEND / '.venv/bin/alembic'), *args],
            cwd=BACKEND, env=migration_env, capture_output=True, text=True, timeout=120,
        )

    subprocess.run(['dropdb', '--if-exists', DB_NAME], env=env, check=True)
    subprocess.run(['createdb', DB_NAME], env=env, check=True)
    engine = create_engine(url)
    previous_override = app.dependency_overrides[get_db]
    try:
        old = migrate('upgrade', PREVIOUS)
        assert old.returncode == 0, old.stderr
        with Session(engine) as session:
            bootstrap_admin_if_needed(session)

            def target_db():
                yield session

            app.dependency_overrides[get_db] = target_db
            login_admin(client)
            legacy_company = create_company(client, name='Migration continuity QA')
            # End the response serializer's read transaction before ALTER TABLE.
            session.rollback()
            upgraded = migrate('upgrade', 'head')
            assert upgraded.returncode == 0, upgraded.stderr
            heads = migrate('heads')
            assert heads.returncode == 0, heads.stderr
            head_lines = heads.stdout.strip().splitlines()
            assert len(head_lines) == 1, heads.stdout
            expected_head = head_lines[0].split()[0]
            with engine.connect() as connection:
                assert connection.scalar(text(
                    'SELECT COUNT(*) FROM companies WHERE id=CAST(:id AS uuid)'
                ), {'id': legacy_company['id']}) == 1
            # The old schema contains real company data. Create the financial
            # transaction only after the migration has added the nullable
            # remittance attribution column used by the current ORM.
            path, bank = _invoice(client, 'ar', approve=True)
            partial = client.post(path + '/receipts', json={
                'treasuryAccountId': bank['id'], 'amount': '25.00', 'receiptDate': '2026-01-20',
            })
            assert partial.status_code == 201, partial.text
            invoice_id = path.rsplit('/', 1)[-1]
            session.rollback()

            def persisted():
                with engine.connect() as connection:
                    return connection.execute(text(
                        'SELECT status, amount_collected FROM customer_invoices WHERE id=CAST(:id AS uuid)'
                    ), {'id': invoice_id}).one()

            assert persisted() == ('PARTIALLY_COLLECTED', 25)
            rejected = migrate('downgrade', PREVIOUS)
            assert rejected.returncode != 0
            assert 'Cannot narrow invoice status' in rejected.stderr
            assert persisted() == ('PARTIALLY_COLLECTED', 25)
            with engine.connect() as connection:
                assert connection.scalar(text('SELECT version_num FROM alembic_version')) == expected_head
                assert connection.scalar(text(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='customer_invoices' AND column_name='status'"
                )) == 32
    finally:
        app.dependency_overrides[get_db] = previous_override
        engine.dispose()
        subprocess.run(['dropdb', '--if-exists', DB_NAME], env=env, check=True)
