# S4P migration and modernization

## Source of truth
- Source: Clopezgg/nexora-group, branch main, read-only.
- Destination: Clopezgg/S4P-, branch main.
- Preserve SAP Fiori / SAP GUI visual identity, design tokens, layouts, brand assets, and functional behavior.
- Maintain FastAPI and PostgreSQL; do not substitute D1 without an explicit compatibility and transactional review.

## Scope
- Executive home; Projects/WBS; Finance/Treasury/Accounting; Procurement;
  Inventory; Operations; Approvals/Audit; Administration/RBAC.
- Stabilize CI before declaring release ready.
- Validate purchase-to-pay including stock, AP, treasury, accounting, reversals, audit and idempotency.
- Make infrastructure portable; use Cloudflare for frontend and edge security.
- Python backend and PostgreSQL require separately provisioned hosting.
- Add production smoke, E2E, backup/restore and security validation before launch.

## Guardrails
- No production data migration or live release without a tested rollback.
- No fabricated responses, business metrics or test success claims.
- No source repository writes.
- Never commit credentials; audit config and GitHub Actions before enabling any deployment.
