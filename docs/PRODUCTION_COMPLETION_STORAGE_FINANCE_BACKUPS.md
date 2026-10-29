# S4P: documentación, finanzas y protección de datos

Actualizado 2026-10-29. **Esta guía distingue configurado de certificado.**

## 1. Evidencias privadas (Supabase)
Creados y verificados en el proyecto Supabase `klnfxzyccohplnzbdecy`:
- Bucket `s4p-evidence-private`, `public=false`, máximo 25 MiB/archivo.
- Bucket `s4p-db-backups-private`, `public=false` (solo copias cifradas).
- El examen de seguridad de Supabase no devolvió avisos inmediatamente tras crear el primer bucket.

### Evidencias activas en producción — confirmado 2026-10-29 UTC

El backend Render `s4p-erp-api` utiliza `EVIDENCE_BACKEND=supabase_edge` y el bucket privado `s4p-evidence-private`. No hace falta generar claves S3 manuales: el puente Supabase Edge `s4p-evidence-bridge` verifica solicitudes Ed25519 firmadas desde Render. **La clave privada de firma se guarda solo como variable secreta de Render; la clave administrativa Supabase permanece dentro del runtime Supabase Edge**. Ningún token administrativo se incluye en React ni en GitHub.

Archivos: `supabase/functions/s4p-evidence-bridge/index.ts`, `backend/app/integrations/supabase_edge_storage.py`, `backend/verify_evidence_storage.py`, `backend/tests/test_supabase_edge_storage.py`. La API de evidencias mantiene las autorizaciones originales de empresa/proyecto de NEXORA. Los archivos solo pasan por FastAPI para imponer RBAC y no se publican URLs directas de Storage.

**Prueba real confirmada:** el despliegue Render del commit `79b4915d9ad01e160d95601b719c398528bbbda6` alcanzó el estado `live`; los logs registraron `PASS: private evidence backend upload/download/delete verified`. Se subió un PDF sintético al bucket privado, se recuperó byte por byte y se eliminó; la posterior consulta de Supabase devolvió cero objetos de evidencia, lo esperado tras la limpieza. `/api/readyz` devuelve HTTP 200 comprobando PostgreSQL y alcanzabilidad del bucket. Pruebas de contrato del puente firmadas: GitHub Actions `40816616310` aprobadas. No se han creado evidencias de negocio artificiales.

Para rotar el secreto de firma, **generar un par Ed25519 nuevo y coordinar su clave pública en Supabase Edge y su clave privada en Render en la misma ventana de despliegue**; verificar con la prueba sintética antes de declarar el servicio listo. Nunca registrar la clave privada, ni pegarla en GitHub, ni reutilizar secretos de usuario.

**Pendiente para certificación funcional total:** prueba con una sesión de administrador real desde navegador móvil, adjuntar un documento a una entidad real y revisar permisos entre múltiples empresas, sin sustituir el test automatizado por un 200 de salud. El almacenamiento ya funciona en el servidor.

## 2. Finanzas
El workflow `S4P financial transaction certification` ejecuta pruebas sobre PostgreSQL 16 aislado (compras, contabilidad, tesorería, inventario, caja y conciliación), sin acceso a fondos reales. La certificación de **producción** requiere además pruebas de solo lectura de `readyz`, permisos y registros, y una secuencia de transacciones de demostración autorizada y reversible, usando una empresa de test sin datos reales.

No se debe automatizar transferencia de dinero ni escribir movimientos de prueba en el libro de producción sin un ámbito de demostración explícito.

## 3. Respaldo cifrado real y base permanente

### Copias cifradas ya operativas (29 octubre 2026 UTC)

El servicio Render tiene `S4P_BACKUP_SCHEDULE_ENABLED=1` y el secreto `S4P_BACKUP_AES_KEY_B64` configurados **privadamente**. Durante el arranque y cada hora mientras el contenedor esté activo, el trabajador `backend/app/services/backup_worker.py` consulta si han transcurrido al menos 23 horas desde la última copia. El job de GitHub `S4P production external read-only smoke` despierta/verifica periódicamente el servicio y permite alertar si un respaldo envejece más de 36 horas mediante `GET /api/backupz`. Como Render Free puede dormir, no constituye un cron de tiempo garantizado.

**Primera copia real confirmada:** registro Render `PASS: encrypted offsite PostgreSQL snapshot committed, chunks=1 bytes=410325` a las 04:32:49 UTC. Supabase respondió 3 objetos privados en `s4p-db-backups-private`: un fragmento cifrado con AES-256-GCM, un manifiesto con hashes SHA-256 y `db-backups/latest.json` publicado solo tras verificaciones remotas. El contenido descifrado nunca sale de Render. Una nueva verificación descargará y descifrará la copia real con `pg_restore --list` para confirmar el formato, sin restaurar ninguna fila en producción.

La infraestructura usa `supabase/functions/s4p-db-backup-bridge/index.ts` (función privada con firmas Ed25519), `scripts/s4p_backup.py` (AES-256-GCM), `backend/app/services/backup_worker.py` y `backend/restore_from_supabase.py` para restauración **solamente en PostgreSQL local aislado**. El código y el contenedor tienen pruebas automatizadas aprobadas, incluidas pruebas criptográficas que rechazan copias manipuladas y un simulacro de `pg_restore` en PostgreSQL desechable.

**Recuperación de emergencia:** conservar fuera de Render y de GitHub el archivo de claves privado entregado por ChatGPT, que incluye `S4P_BACKUP_AES_KEY_B64` y la clave de firma del puente Edge. **Sin ambos secretos, descargar o descifrar copias podría resultar imposible.** No subirlo al repositorio. En un equipo de recuperación con Python, dependencias y `pg_restore` instalados, preparar `EVIDENCE_BACKEND=supabase_edge`, `EVIDENCE_CONTAINER_NAME=s4p-evidence-private`, `SUPABASE_EDGE_BRIDGE_URL`, ambos secretos y ejecutar `python backend/restore_from_supabase.py --target-database-url postgresql+psycopg://usuario:clave@localhost:5432/s4p_restore_isolated`. La base destino debe ser local, vacía y aislada. Este procedimiento completo sobre datos reales deberá ensayarse en una instancia de recuperación independiente.

### Riesgo pendiente: base PostgreSQL temporal

La base activa `s4p-postgres-staging` continúa en Render Free y expira el **27 de noviembre de 2026**. Las copias externas ahora protegen información contra pérdida definitiva, **pero no evitan la interrupción del ERP** si la base gratuita desaparece. La continuidad de operaciones requiere contratar/provisionar un PostgreSQL persistente con política de restauración, o migrar con prueba transaccional a Supabase Postgres sin transferir secretos a GitHub. No crear planes facturables sin aprobación explícita.

## Criterios para cerrar
- Evidencia: almacenamiento privado con subida/descarga/borrado reales aprobado; resta validación por navegador y usuarios/empresas reales, con auditoría y persistencia tras un nuevo despliegue.
- Finanzas: CI verde + pruebas de negocio con empresa sintética y reversión/auditoría sin datos reales.
- Permanencia: copia externa cifrada real establecida y monitoreo de frescura; siguen pendientes PostgreSQL sin caducidad y ensayo de restauración completa sobre copia de producción en un entorno aislado.
- Nunca considerar `Live` del servidor como certificación de estas tres capacidades.
