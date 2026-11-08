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
