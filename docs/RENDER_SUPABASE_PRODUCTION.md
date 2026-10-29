# S4P — Render + Supabase production cutover (authoritative)

This document replaces prior Cloudflare-first hosting suggestions for the CURRENT deployment. The SAP visual identity, React, TypeScript, FastAPI, PostgreSQL and all financial/domain constraints remain intact.

## Verified topology (2026-10-28)
- Source: https://github.com/Clopezgg/S4P- (origin nexora-group is not modified).
- Canonical combined web+API service: https://s4p-erp-api.onrender.com (not ready as of writing).
- Render service ID: srv-dbh8ihec6qcc73em0ho0, Dockerfile.render: builds SPA and FastAPI together, autoDeploy disabled until validated.
- Public static preview: https://s4p-sap-preview.onrender.com (not production; no valid /api backend).
- Supabase project ref: klnfxzyccohplnzbdecy; private schema `s4p` and role `s4p_runtime` created; Alembic migrations NOT applied there.
- Render free PostgreSQL `s4p-postgres-staging` exists as a temporary fallback, expires 2026-11-27; NOT suitable as primary durable production.
- Latest full CI: inspect GitHub Actions. Any past green check is an isolated test database, NOT a production certificate.

## Mandatory connection without revealing secrets to a chat
1. In Supabase dashboard: Project `nexora-group` → Connect → Postgres connection strings → **Session pooler, port 5432** for the region/project. Render free services may need an IPv4-compatible pooler; the direct host may be IPv6-only.
2. Use an appropriately restricted Postgres role with a real authenticated password. An existing role without a password is *not* a usable application login. Preserve `s4p` isolation: database role must own/use CREATE in its own schema and have search_path set to `s4p,public`.
3. In Render `s4p-erp-api` → Environment, enter the complete `DATABASE_URL` as a secret. SQLAlchemy must use the dialect prefix `postgresql+psycopg://`, host and password URI encoded as needed, and `sslmode=require` (or the provider's documented TLS configuration).
4. Never paste a password/URL in ChatGPT or commit it to the repo. The Render/Supabase connectors currently do not provide a safe cross-app secret-reference action; direct secret injection was blocked by platform security enforcement. Do not disable the protection or open network ACLs.
5. Verify the database user has CREATE/ALTER rights needed for the ~70 Alembic migrations within `s4p`. Be aware some migrations may explicitly assume `public`: inspect and adjust on a clone prior to production promotion.
6. Render Docker startup runs `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`; a failed migration blocks startup correctly.

## Production security requirements
- `APP_ENV=production`; `SECRET_KEY` must be unique, >=32 chars, secret-only.
- `FRONTEND_URL=https://s4p-erp-api.onrender.com` (exact origin).
- `EDIT_ACCESS_REQUIRED=true` requires a valid PBKDF2 salt/digest corresponding to a **known PIN**, set by the operator through a trusted secret mechanism. A random unmatched digest is NOT a working PIN.
- `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` should be set with a strong one-time password via Render secrets; bootstrap creates an administrator ONLY if the database initially has no users. Rotate/revoke the bootstrap values after first login.
- `EVIDENCE_BACKEND=none` disables evidence storage, so do NOT advertise the ERP as fully functional for any workflow requiring uploaded evidence. Configure a tested S3-compatible backend and private evidence bucket with RBAC and upload/download tests before production.
- Disable production promotion until login succeeds in a real browser, company/project isolation is validated, and backup/restore is proven.

## Acceptance evidence (all mandatory)
1. Render deployment status is LIVE (not update_failed).
2. `GET https://s4p-erp-api.onrender.com/api/healthz` gives JSON status ok, and `/api/readyz` returns 200.
3. Alembic `upgrade head` and `alembic current` are verified in the target DB; verify tables are in intended schema and no user data was overwritten.
4. Login via `POST /api/auth/login` returns authenticated user, sets Secure HttpOnly cookie; `GET /api/auth/me` succeeds with cookie. Failure/lockout/CSRF protections also tested.
5. Real purchasing-to-payment flow checks authorization, idempotency, financial double-entry, inventory linkage, tenant isolation and reversal.
6. Evidence upload/download, reports, branding, session cookies (Safari), dashboards and responsive UI verified.
7. Full GitHub CI green, production readiness workflow green, backups and restore exercised, no mock values in production.

## Infrastructure boundaries
- Render static preview is frontend-only; do not use as canonical login URL.
- No secret is needed for `frontend/dist`; it accesses same-origin `/api` when hosted in Dockerfile.render.
- Render free Postgres expires. Supabase free quotas / limited backup durability require a plan before entrusting irreplaceable financial records.
- Existing NEXORA source repository remains unchanged.
