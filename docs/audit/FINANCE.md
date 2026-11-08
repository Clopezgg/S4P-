# Reglas financieras y evidencia exigida

GL es la verdad contable; Treasury custodia el dinero; Project/WBS atribuye costo y presupuesto. `CENTRAL`/`GENERAL` requieren project_id NULL; `PROJECT` requiere proyecto. El contexto UI nunca determina por sí solo el scope de una operación.

`posting_service` valida suma Decimal de débitos/créditos, total distinto de cero, líneas sin debe y haber simultáneos ni valores negativos, periodo abierto, compañía de cuenta/proyecto/centro y numeración. Los hooks de reverso sincronizan documentos fuente; no basta con invertir el GL. `JournalLineInput` usa Decimal; la presentación central cuantiza dos decimales con ROUND_HALF_UP. Cada canal de entrada sigue necesitando validar escala, moneda y NaN/Infinity; un formatter no es control contable.

| Invariante | Implementación a revisar | Regresiones reales disponibles |
|---|---|---|
| Doble partida / restricciones DB | posting_service, accounting models y Alembic | test_posting_engine, financial_properties, fiscal_db_integrity |
| Scope y aislamiento | financial_validation_service, permission_service | operation_scope_constraint, project_scope_access, rbac_and_company_isolation |
| Idempotencia / carreras | idempotency_service, locks de proyecto/periodo | concurrency, fiscal_serialization, project_setup_concurrency, idempotency_service |
| Factura/aprobación/pago | ap_service, approval_service | ap_ar, approvals, approval_assignment, contract_payment_failclosed |
| Contratos/retención/anticipo | contract_payment_service | contract_retention_lifecycle, contract_advance_schedule, advance_duplicate_reconciliation |
| Remesas / gastos / saldo | treasury_service | treasury_financial_flows, treasury_invariants, treasury_direction |
| Reverso y conciliación | financial_reversal_service, posting hooks | financial_reversals, payment_receipt_reversals, subledger_gl_reconciliation |
| Recibo y evidencia | voucher_service, voucher_issuance/verification | company_branding_voucher, evidence_download, voucher_beneficiary_address |

QA local usa exclusivamente el contenedor `s4p-audit-pg`, PostgreSQL 16, puerto loopback 5432; pytest usa nexora_test_s4p y Playwright nexora_e2e. Las migraciones se aplican solo a bases locales recién creadas. No se ejecutan escrituras financieras en Render/Supabase.

La suite existente prueba 13 fases reales + raíz, idempotencia y rollback; la critical journey cubre factura/pago, GL, reversos, conciliación y descarga PDF. Esto **no demuestra automáticamente un solo ciclo residencial completo** con reinicio, adjuntos y todos los roles. Ese escenario, la persistencia tras reinicio y la inspección de cada acción de cada pantalla siguen siendo gates hasta evidencia específica. Un test que activa un contrato directamente por SQL no prueba la aprobación de ese contrato mediante UI.

Ejecución posterior: 57 casos financieros/seguridad pasaron sobre PostgreSQL aislado (64.10s), incluidas 13 fases, idempotencia/rollback, posting Decimal, RBAC, reversos y conciliación GL. Además pasó la nueva regresión PDF de efectivo, y el dataset de GL/empresa/roles/recibo persistió tras reinicio real de PostgreSQL. Ver EXECUTION.md y evidence. El ciclo contractual residencial único completo sigue PARCIAL.
