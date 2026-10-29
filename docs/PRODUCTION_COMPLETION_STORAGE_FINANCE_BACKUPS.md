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

## 3. Base permanente y copias de seguridad
Render PostgreSQL free `s4p-postgres-staging` expira **2026-11-27** y no incluye copias administradas. **No es duradero ni adecuado para datos financieros reales.**

Ya existe `scripts/s4p_backup.py`: ejecuta `pg_dump -Fc` autenticado, cifra con AES-256-GCM, carga un blob a un bucket S3 privado y valida que exista; `restore-verify` solo permite restaurar contra otra base local separada. El CI incluye prueba de cifrado, detección de manipulación y restauración exacta. Nada de esto implica que exista hoy un backup de producción.

**Para activar backups** se necesita un ejecutor con acceso a la base de Render (misma región/red privada), credenciales S3 y clave AES de 32 bytes protegida. No usar cron gratuito supuestamente persistente: Render cron jobs tienen cargo mínimo mensual y requieren autorizarlo; tampoco es seguro abrir PostgreSQL a Internet para GitHub Actions. Un servicio cron de pago o migrar a una base duradera con backups gestionados son opciones posteriores a autorización explícita de costos.

Variables requeridas para la tarea de backup (solo secrets de un ejecutor de confianza):
- `DATABASE_URL` (una cuenta de respaldo de lectura suficiente, no compartida públicamente).
- `S4P_BACKUP_AES_KEY_B64`: clave AES de 32 bytes en Base64, guardada **también en un segundo lugar seguro**; sin ella no se puede restaurar.
- `S4P_BACKUP_S3_ENDPOINT`: endpoint HTTPS S3.
- `S4P_BACKUP_S3_REGION`: región.
- `S4P_BACKUP_S3_BUCKET=s4p-db-backups-private`.
- `S4P_BACKUP_S3_ACCESS_KEY_ID`, `S4P_BACKUP_S3_SECRET_ACCESS_KEY`: credenciales privadas del destino.

Usar `python scripts/s4p_backup.py backup` con PostgreSQL client tools y `boto3 cryptography` instalados. Comprobar cada copia mediante restauración de prueba **fuera** de la instancia productiva; registrar fecha, resultado, integridad y retención. El cifrado no sustituye política de retención, alertas ni backups administrados.

## Criterios para cerrar
- Evidencia: almacenamiento privado con subida/descarga/borrado reales aprobado; resta validación por navegador y usuarios/empresas reales, con auditoría y persistencia tras un nuevo despliegue.
- Finanzas: CI verde + pruebas de negocio con empresa sintética y reversión/auditoría sin datos reales.
- Permanencia: base no caducable, copia externa diaria real, alerta ante fallo y una restauración ensayada.
- Nunca considerar `Live` del servidor como certificación de estas tres capacidades.
