# S4P ERP — Residential project transformation and production acceptance

Date: 2026-10-30. This is a **live gate**, not a completion certificate.

## Delivered in this branch
- Official first-party residential WBS template: one root plus 13 editable phases.
- Existing atomic/idempotent project setup creates the entire template inside one PostgreSQL transaction; any failure rolls the project and all WBS phases back.
- No baseline, funds, payment, contract, dates, or transactions are invented.
- Guided "Nueva residencia" start, and draft creation from the first step. Generic/manual project creation remains supported.
- Project detail navigation links to real Treasury, procurement, contracts, installment ledger, vouchers and documents.
- S4P Horizon is the default for new browser installations; saved account/company theme choices continue to have priority.
- Visible generic legacy administrator label normalized in the shell; account's stored display name remains unchanged for audit integrity.
- Spanish translations of frequently exposed navigation labels.
- Authentication cache isolation from merged PR #5.

## Blocking production gates (not certified)
1. **Data permanence:** Current Render free PostgreSQL expires on 2026-11-27. Supabase private `s4p` schema exists but application migrations and business records have NOT been migrated. Do not switch DATABASE_URL to an empty database or delete the existing instance.
2. **Restore rehearsal:** Encrypted private Supabase backup files exist, but independently verified database restore and row/accounting reconciliation on an isolated destination are not yet documented as passed.
3. **Live browser journeys:** With an authorized test company and test user, certify: login; company/project creation; 13 WBS phases; budget; capital/remittance; account association; supplier/contract; monthly installments; invoice approval and payment; receipt PDF; treasury/GL reconciliation; document access; rollback and re-login.
4. **Security:** GitHub main branch protection and review gates must be enforced at repository level, account/company/project access isolation requires live certification. Do not place production secrets in GitHub files or chat.
5. **Runtime parity:** This repo's canonical deployment is Render `s4p-erp-api`. Keep auto-deploy disabled until CI and explicit release decision. The static preview and old NEXORA service are not authoritative.
6. **Administration:** Original bootstrap administrator name may still exist in the database. Only update the underlying name using an authenticated, audited authorized account operation; the UI alias is not a database migration.
7. **Product scope:** Account setup, remittances, supplier invoices, contract payments, receipts, WBS budgets and GL all have substantial implementations but need user-realistic integrated test evidence. No claims of 100% prior to that evidence.

## Mandatory financial invariants
- Monetary amounts in backend must remain Decimal/Numeric; currency explicit.
- Capital contributions, liabilities and revenue are classified by the ledger; do not equate all remittances to earned income.
- Payments and contractual installments must be idempotent and traceable; never mark paid from a UI-only state.
- Existing financial and audit entries are retained, reversals are explicit, and no destructive re-seeding is permitted.
- Private uploads remain behind company and project RBAC, no public object URLs.
- No fake KPI or "zero" standing in for missing source data.

## Rollout gate
- Merge only on CI green.
- Trigger a manual Render deployment, verify exact merged SHA and /api/healthz /api/readyz.
- Run authenticated end-to-end tests and compare real WBS/project data after restart.
- Check rollback and recent encrypted offsite backups.
- Mark release 100% only when all blockers above have independently verifiable evidence.

Do not interpret historical Azure or NEXORA documentation as current Render architecture.
