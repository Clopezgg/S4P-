# Arquitectura y trazabilidad

React/TypeScript/Vite sirve dos shells sobre las mismas rutas y servicios. `frontend/src/app/routes.tsx` carga pantallas; `navigation.ts` define navegación y permisos UX. TanStack Query mantiene datos; React Hook Form/Zod valida formularios; `httpClient.ts` añade cookies y capacidad de edición. El backend FastAPI monta routers y middlewares de correlación, CSRF, edición protegida y headers. `get_current_user` resuelve sesión persistente; `permission_service` aplica RBAC y alcance empresa/proyecto. Servicios coordinan dominio; repositorios/SQLAlchemy persisten en PostgreSQL; Alembic instala esquema y triggers.

| Flujo | UI → API | Servicio / regla | Persistencia / auditoría / corrección |
|---|---|---|---|
| Login/sesión | LoginPage → auth/login, auth/me, auth/logout | auth_service; Argon2, bloqueo, límites, expiración | users, sessions y registros de seguridad; logout revoca token |
| Proyecto/13 fases | ProjectWizard → projects/setup-runs → execute | project_setup_service, RESIDENTIAL_HOUSE_V1, idempotencia | Project, raíz WBS + 13 fases, ProjectSetupRun; auditoría create/complete/fail; fallo debe revertir unidad de trabajo |
| Presupuesto | pantallas WBS/budget → project-budget/project-control | budget_service, revisiones y compromiso | Budget y líneas; aprobar/revisar según estado; no crea efectivo |
| Banco/caja/remesa | TreasuryPage → treasury/accounts, remittances | treasury_service; origen determina tipo de contrapartida | TreasuryAccount, Remittance, ledger, documento GL, auditoría; reverso formal |
| Contrato/cuotas | SupplierContractsPage/ContractPaymentPlanModal → procurement/suppliers/contracts, contract-payments | contract_payment_service, plan, anticipos, retenciones | SupplierContract y calendario; corrección/enmienda según estados; no doble contabilización |
| Factura/pago | AccountsPayableWorkspace/SupplierInvoiceFlows → ap/supplier-invoices y supplier-payments | ap_service, approvals, posting_service; SoD, periodo, saldo | SupplierInvoice/Payment, JournalLine, AccountingSourceLink; auditoría en unidad transaccional; reverso enlazado |
| GL/conciliación | AccountingPage/BankReconciliationPage → accounting/treasury | posting_service, subledger reconciliation y treasury | documento inmutable y líneas Decimal; conciliación debe referenciar movimiento correcto; corrección por reverso |
| PDF/evidencia | VouchersPage → treasury/vouchers; evidence | voucher_service, issuance, verification, evidence_service | snapshot de emisión, token verificable y vínculo al documento; storage privado; no borrar asiento al borrar archivo |

Los routers normalmente solicitan `commit=False` al servicio, registran audit y confirman juntos; inspeccionar cada endpoint en el inventario antes de generalizar atomicidad. `get_db` cierra sesión y las rutas relevantes hacen rollback en fallos; no se presume rollback de efectos externos de storage. El handler de errores convierte excepciones de dominio en errores HTTP con correlación.

Inventario backend comparado: 249 archivos idénticos a Nexora, 3 con solo sustitución de marca, 5 exclusivos S4P y 13 con diferencias que requieren revisión. No hay base para declarar todos esos cambios regresiones. `voucher_service.py` difiere solo en marca. Las diferencias funcionales principales están en auth/bootstrap, guards, configuración, salud, storage y setup residencial; los archivos se enumeran en `backend_comparison` del JSON.

Jobs: backup daemon opt-in en lifespan (thread por proceso), scripts de backup/restore y workflows de backup, bridge, finanzas, smoke y release. La existencia de cron/workflow no demuestra ejecución ni RPO. Revisar todos los workflows en el inventario, además de los seis obligatorios.
