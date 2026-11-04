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
- `s4p-release-provenance.yml`: manually-run production read-only gate; rejects any deployed SHA differing from `main` and checks readiness and fresh offsite backups.
- These jobs complement, not replace, existing transactional CI, backup checks and production login certification.

## Dependency scan findings discovered 2026-11-03
- Python: upgrade the cryptography dependency floor to 48.0.1 (reported fix for the seven pip-audit advisories); do not close until the job is green.
- Frontend: the new npm audit found six high-severity alerts in the current lockfile. A dependency/lockfile upgrade with passing full test suite is a P0; do not bypass or downgrade the scanner to obtain green checks.
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
