# Registro de defectos

| ID / prioridad | Evidencia y causa raíz | Reparación / estado |
|---|---|---|
| AUD-001 P0 | scripts/db_restore.sh llamaba dropdb --if-exists sin validar host/nombre; destruía el destino existente, incluso remoto por PGHOST/servicio | Reparado: local explícito, prefijo QA, rechazo overrides de conexión, createdb sin drop, restore atómico/fail-fast. Regresiones shell + PostgreSQL real y repetición preservando GL/empresa |
| AUD-002 P0 | Render PG16 free vence 2026-11-27; Supabase cero tablas ERP | BLOQUEADA liberación: preparar/autorizar base permanente y cutover con recuperación |
| AUD-003 P0 | Existen objetos privados cifrados, pero no restauración cifrada real accesible en este entorno | BLOQUEADA certificación; no confundir fixture local con backup productivo |
| AUD-004 P0 | Protección main no verificable por integración (403); rollback real no ejercitado | Pendiente evidencia administrativa y simulacro autorizado |
| AUD-005 QA | Instalación de navegadores + WAL agotó disco; fallos DiskFull/ENOSPC en backend y navegador | Se purgaron caches de paquetes, se retiró navegador headed no usado y se limitaron checkpoints solo en PG local; repetir ejecuciones afectadas, no imputar a negocio |
| AUD-006 QA | WebKit carecía de dependencias del sistema | Instalación local de bibliotecas y arranque real conseguido; resultados de escenarios en evidencia de ejecución |

No se declara libre de defectos al resto del ERP por ausencia de fallos en un muestreo. Las 13 diferencias funcionales frente a Nexora requieren revisión individual; 249 archivos backend son idénticos, 3 solo marca y 5 exclusivos S4P.

AUD-007 P2, dependencias: npm audit encuentra ocho alertas (seis moderate/dos low), ninguna high/critical. Afectan herramientas Vitest/PWA y transitivas. No se altera el umbral del workflow ni se fuerza un downgrade/override para obtener cero. JSON en evidence/npm-audit.json; resolución compatible pendiente.

## Reparaciones financieras posteriores — 2026-11-09

- **AUD-008 P0 — commit antes de auditoría.** Ocho rutas tenían confirmación anticipada: remesa, pago AP, cobro AR, aprobación de cierre de caja, envío/aprobación/cancelación AP y aprobación AR. Siete rutas accesibles reprodujeron persistencia indebida ante fallo de audit; cancelación estaba además bloqueada por permiso ausente. Reparación: servicios con `commit=False` desde API, audit y respuesta idempotente dentro del commit final; flags compatibles para callers de servicio. La prueba inyecta exclusivamente fallo de escritura de audit y compara desde conexión nueva GL, documentos, facturas, pagos/cobros, cierre, idempotencia, aprobación y notificación. No simula el movimiento ni la DB. Pasa con y sin Idempotency-Key.
- **AUD-009 P1 — cobro parcial AR roto.** `PARTIALLY_COLLECTED` excedía VARCHAR(16): PostgreSQL devolvía StringDataRightTruncation y el cobro no se registraba. Modelo y migración `7b2c1af4849c` amplían a 32. Regresión real: 25 + 75 sobre factura 100 pasa por PARTIALLY_COLLECTED y COLLECTED. Upgrade desde revisión anterior con datos probado; downgrade con estado largo se rechaza sin truncar datos.
- **AUD-010 P1 — dos acciones inaccesibles por RBAC.** Las rutas AP cancel y update de referencia exigían permisos que no existían en `_BASE_PERMISSIONS`; ni Administrator podía ejecutarlas. Se registran ambos permisos, otorgados por la matriz existente solo a Administrator. Regresión API: administrador cancela borrador/corrige referencia, Auditor recibe 403 y el dato permanece. Prueba estática recorre todos los `require_permission` literales de routers y exige que existan en catálogo.

La migración se ejecutó únicamente en bases locales desechables. Producción NO fue migrada; desplegar este nuevo head exige aprobar y verificar por separado el cambio de esquema. Dockerfile.render conserva el gate read-only y bloqueará una DB anterior.
