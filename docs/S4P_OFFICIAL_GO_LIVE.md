# S4P ERP — Corporate production acceptance (2026-11-03)

This file is a **release gate**, never an assertion that S4P is already certified.

## Authoritative environment
- GitHub: `Clopezgg/S4P-`, `main`.
- Production SPA + FastAPI: `https://s4p-erp-api.onrender.com`; automatic deployment remains **disabled**.
- Render PostgreSQL `s4p-postgres-staging` is the current source-of-truth until a verified cutover. Its free instance reports expiration **2026-11-27**.
- Supabase `klnfxzyccohplnzbdecy` hosts private evidence and encrypted backups. The `s4p` business schema is **not** a replicated production ERP database. Do not point the application to it until migrations, restore and reconciliation pass.
- The historical Nexora instance and S4P static preview are **not** production authorities.

## Added CI/CD controls
- `s4p-secret-scan.yml`: Gitleaks v3 on changes introduced by PRs and pushes (a separate full historical review remains necessary).
- `s4p-codeql.yml`: Python and TypeScript static analysis.
- `s4p-dependency-audit.yml`: npm and pip vulnerability checks.
- `s4p-browser-e2e.yml`: actual browser, PostgreSQL, authenticated critical journey, private Azurite test storage and screenshot/trace evidence on failures.
- `s4p-release-provenance.yml`: manually-run gate that **fails closed** until protected GitHub `production` environment variables `S4P_DB_CUTOVER_CERTIFIED=true`, `S4P_RESTORE_DRILL_CERTIFIED=true` and `S4P_FINANCE_E2E_CERTIFIED=true` are set only after independent evidence; then rejects deployed SHA mismatches and checks readiness and fresh offsite backups.
- These jobs complement, not replace, existing transactional CI, backup checks and production login certification.

## Dependency scan findings discovered 2026-11-03
- Python: upgrade the cryptography dependency floor to 48.0.1 (reported fix for the seven pip-audit advisories); do not close until the job is green.
- Frontend: initial audit found six high-severity alerts. The candidate lockfile has since been updated; the blocking high/critical audit passed. Remaining low/moderate findings require documented triage, while full backend + browser E2E remains a mandatory release gate.
- Test-only Azurite uses its built-in emulator development connection; no test account keys in the repository workflow.

## P0: No irreversible business operations until these have evidence

1. **Data migration and continuity:** obtain an isolated full `pg_dump` of the current Render PostgreSQL through a privileged internal/private route. Restore it into an isolated target; compare row counts, primary/foreign keys, Alembic head, authorization roles, document references and accounting sums. PostgreSQL 16 → 17 differences require a dry run. Never apply migrations to an unknown or empty production target. The hosted Render connector cannot query the database while external IP allowlist is empty; do not weaken the network ACL to work around this limitation. Choose secure CLI/SSH/internal transfer.
2. **Backup/restore:** decrypt a *real* offsite production backup in an isolated recovery environment using approved secrets without printing them. Run `pg_restore`, validate company/project/user counts, vouchers, posted journal lines and `SUM(debit)=SUM(credit)`, then start a disposable FastAPI pointing only to that restored database. Validate storage and document references separately.
3. **Login and session:** configure `S4P_SMOKE_EMAIL`/`S4P_SMOKE_PASSWORD` as protected GitHub production environment secrets for the existing `s4p-production-login.yml`; execute it, then check login/logout and identity isolation on a mobile Safari browser.
4. **Business critical journey:** in a dedicated QA company, create company → project → 13 residential WBS phases → budget → treasury account → correctly classified remittance → supplier → contract → installment schedule → invoice → approved payment → PDF receipt and supporting evidence → GL/reconciliation → reversal. Check persistence after restart. **Never seed financial demo data into a live company**.
5. **Security governance:** configure a `main` branch ruleset from GitHub settings: review before merge and require green S4P validation, browser E2E, CodeQL, Gitleaks, dependency audit and relevant financial workflows. The installed connector cannot enforce branch protection through its permission scope; a repo admin must apply it in GitHub Settings.
6. **Version / deployment:** only merge after CI green; deploy exact `main` SHA manually to Render and run `s4p-release-provenance.yml`. Verify rollback steps and retained data before enabling business users.
7. **Training & operational readiness:** approve company identity, fiscal settings, chart of accounts, banks, permissions, document numbering, contractual approval policy and immutable posting rules. Provide a short operator manual and financial exception handling.

## Acceptance criteria
- No expiring **primary** database, restore drill passed against **real** snapshot, and monitored backups with an approved recovery objective.
- GitHub PR and `main` CI all green for **exact** release SHA; Render serves that SHA.
- Production browser, auth, business flow, AP/AR/Treasury/GL and evidence test evidence attached to the release; isolated tenant/security tests passing.
- Corporate S4P branding visible and responsive in Safari/desktop; legacy technical identifiers only changed with a tested compatibility migration.
- A named operator approves go-live; financial operations never rely solely on an HTTP health check or a passing mocked test.

## Safe cleanup after certification
- Archive rather than delete historical Azure/Nexora artifacts that provide rollback/audit evidence.
- Replace legacy **public-facing** strings and user manuals; do not rename persisted cookie names, event topics or schema identifiers without compatibility tests.
- Retire the old Render `nexora-group` service and S4P static preview **after** confirming no users depend on them and preserving rollback capability.
- Remove redundant deployment paths only after the canonical Render + Supabase configuration is reproducible.

**Status (2026-11-03): NOT CERTIFIED — do not claim official go-live.**


## Production PostgreSQL parity tool (read-only)

After restoring the real Render backup to a **separate** PostgreSQL target,
run the following from a secured worker with private access to both servers:

```sh
export S4P_SOURCE_DATABASE_URL='<injected privately; use sslmode=require>'
export S4P_TARGET_DATABASE_URL='<injected privately; use sslmode=require>'
cd backend
python s4p_db_reconcile.py
```

The tool executes read-only transactions on **both** connections and refuses
equal source/target identities. It requires S4P's essential business tables,
compares **every row of every public table** using deterministic SHA-256
fingerprints (including all column values, not merely table counts), the
single Alembic head and critical financial totals, and rejects any unbalanced
posted or reversed accounting documents. It never prints connection strings
or financial records. A mismatch fails with exit code 1. It does not restore,
delete, migrate, change Render `DATABASE_URL` or enable users; the separate
supervised cutover remains an explicit operation after all checks pass.

**Security:** do not paste real DSNs into a GitHub action, shared file, chat,
a terminal recording, or any public log. Use a private secret injection
mechanism. This script does not bypass Render's closed IP allowlist.


## Fail-closed production database startup

The Render application container must not run schema migrations implicitly.
`Dockerfile.render` executes `alembic current --check-heads` before starting FastAPI.
The command reads the current database revision and fails closed when the database
is not at *every* expected head. It does **not** apply migrations, stamp revisions,
modify `DATABASE_URL`, or repair an incompatible database.

Any required schema migration is a separate, supervised release activity:
1. Obtain a verifiable recent production backup and test an isolated restoration.
2. Confirm the source/target database identity and exact released Git SHA.
3. Reconcile Alembic, foreign keys, accounting balances, users and documents.
4. Obtain written human approval and a tested rollback procedure before running
   `alembic upgrade head` against the explicitly approved target using a
   private, authenticated connection; never insert secrets in tickets or logs.
5. Re-run the read-only head check, then deploy and verify `/api/version`,
   `/api/readyz`, `/api/backupz`, access controls and financial QA.

An application startup aborted by the read-only check is **not** authorization
to migrate production automatically or open the database IP allowlist.
