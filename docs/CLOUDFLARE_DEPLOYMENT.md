# S4P — Cloudflare deployment

## Status
Cloudflare account authentication was confirmed previously. No live Cloudflare Pages project, backend, database, or production deployment is certified by this repository. Never mark deployment complete until the Pages URL responds and authenticated API smoke passes.

## Architecture
- Cloudflare Pages: `frontend/dist` built from `frontend`, VITE_API_BASE_URL=/api.
- Pages Functions: `functions/api/[[path]].ts`, reverse proxy to an HTTPS FastAPI service.
- API_ORIGIN: secure fixed backend origin configured in Cloudflare Pages environment variables (e.g. https://api.example.com), with NO trailing path and never a credential.
- FastAPI: existing container with PostgreSQL, secrets, migrations and persistent transaction state.
- R2: optional future replacement for Azure Blob evidence after real adapter and tests.

## Provisioning checklist
1. Keep production private until backend and PostgreSQL exist with backups and tested restore.
2. Create Cloudflare Pages project `s4p-erp`, connect GitHub `Clopezgg/S4P-`.
3. Build command `cd frontend && npm ci && npm run build` from project root, output `frontend/dist`; configure Node 22 and `VITE_API_BASE_URL=/api`.
4. Add production `API_ORIGIN` to Pages Functions environment before releasing to users; do not use `http://`.
5. Use `functions/api/[[path]].ts` as same-origin API proxy and ensure the Pages build includes Functions.
6. Backend `FRONTEND_URL` must exactly match production HTTPS Pages origin. Configure a strong `SECRET_KEY`, edit-access secrets, database URL and object storage.
7. Verify login, cookies in Safari, /api/healthz, /api/readyz, company permissions, project isolation, purchase-to-pay and uploads.
8. Only then expose the application, observe logs and verify backup/restore.

## Warnings
- Hosting a static frontend does NOT mean the ERP backend or PostgreSQL is deployed.
- Cloudflare Pages cannot execute this existing PostgreSQL-dependent FastAPI app as-is.
- Never expose a direct database endpoint to the browser.
- Never promote CI without real PostgreSQL migration and authenticated smoke verification.
