# PostgreSQL, respaldo y recuperación

Lecturas reales 2026-11-08 UTC:

- Render `dpg-dbh8j41srm7s73f3u1b0-a`: PostgreSQL 16, free, available, sin HA, allowlist vacía, vence **2026-11-27 23:47:28 UTC**.
- Query read-only por Render MCP bloqueada expresamente por allowlist. Se mantiene cerrada. No se conoce el head Alembic real ni la integridad de tablas de producción por esta vía.
- Supabase `klnfxzyccohplnzbdecy`: list_tables(public,s4p) devuelve `[]`. No es una base ERP de reemplazo lista.
- Consulta agregada Storage: `s4p-db-backups-private` public=false, 23 objetos, objeto más reciente `2026-11-08 07:28:26.581438+00`; `s4p-evidence-private` public=false, 0 objetos. Un objeto no equivale necesariamente a backup completo; puede ser chunk/manifest/marker.
- `/api/backupz` responde 200 `status=ok`; acredita el contrato del endpoint de la versión desplegada, no restauración, cobertura ni clave recuperable.

Se preparó un PostgreSQL **independiente local**, conservando fsync. Se redujo max_wal_size a 128MB, min_wal_size a 32MB y checkpoint_timeout a 30s para caber en el disco efímero de QA. No cambió configuración de producción.

`test_backup_restore.py` crea origen local, aplica Alembic, siembra datos por servicios, pg_dump, restaura en destino nuevo y verifica empresa, hash Argon2, revisión y debe=haber por el importe real sembrado. La regresión añadida repite restore y comprueba que el rechazo conserva empresa y GL. Nueve pruebas dirigidas pasaron en 14.58s; esto es duración de suite, **no RTO empresarial**.

La restauración de un backup **cifrado de producción** continúa BLOQUEADA: este entorno no tiene clave AES ni credenciales del bridge privado. El conector Storage/SQL no aporta una clave de descifrado ni una sesión de shell autorizada en Render. No se extraen secretos por SQL. El destino aislado ya existe como capacidad; falta acceso al backup y clave por un canal seguro autorizado. No se pide ni publica clave en chat.

RPO de producción no acreditado: fecha de objeto más reciente no prueba punto recuperable. RTO de producción no medido. Faltan verificar FK, head, empresas, roles, recibos/snapshots y saldos sobre restauración real cifrada, y aprobar base permanente antes de caducidad. No se cambia DATABASE_URL ni se ejecuta migración productiva.
