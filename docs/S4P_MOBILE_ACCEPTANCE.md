# S4P mobile web workspace — acceptance and security

This is the **same** S4P responsive web ERP at mobile widths (not a separate native
application or a separate database). All authenticated routes, company scope,
roles, Protected Edit and financial validation continue to use the existing
FastAPI/PostgreSQL backend. Do not fork business logic for mobile.

## Responsive contract

- Widths **360, 390, 430 and 768px**, including iPhone Safari/WebKit.
- One consistent bottom navigation: Home, two RBAC-allowed modules, Create,
  and More. More opens the original permission-filtered menu plus an active
  company selector; no hidden desktop navigation is required.
- SAP workstation uses a compact mobile context bar and scrollable workarea,
  while the desktop SAP menu/toolbar remains unchanged at wider widths.
- Tables built using shared Table/DataGrid become labeled records on small
  screens. Complex native transaction tables must remain internally scrollable;
  no numeric/debit/credit columns may be discarded.
- Finance KPIs stay readable, forms and modals fit the viewport, touch targets
  are at least 44 CSS pixels for primary mobile navigation, and safe-area
  insets protect iPhone controls.
- Manifest supports adding the **online-only** web application to the home
  screen. Do not add offline caching of authentication, receipts or financial
  documents without a separate reviewed data-protection design.

## Evidence gates

The GitHub Actions functional suite runs `mobile-workspace.spec.ts` in
Chromium and iPhone WebKit against the isolated PostgreSQL E2E database,
checking visible navigation, drawer, company picker, quick-create sheet,
responsive routes, narrow screen overflow, and manifest. The existing
visual suite still audits all navigable routes and the four SAP variants at
desktop/tablet/mobile widths. Never remove the previous accessibility,
finance or desktop coverage to get green.

Render's static preview may deploy this frontend automatically, but it
**redirects to the canonical backend** by design. It is not proof that
the new code is served by the production FastAPI service. The production
backend must be deployed deliberately to the approved SHA only after
corporate P0 gates (per `docs/S4P_OFFICIAL_GO_LIVE.md`) have passed.
