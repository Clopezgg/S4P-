# S4P: documentación, finanzas y protección de datos

Actualizado 2026-10-28. **Esta guía distingue configurado de certificado.**

## 1. Evidencias privadas (Supabase)
Creados y verificados en el proyecto Supabase `klnfxzyccohplnzbdecy`:
- Bucket `s4p-evidence-private`, `public=false`, máximo 25 MiB/archivo.
- Bucket `s4p-db-backups-private`, `public=false` (solo copias cifradas).
- El examen de seguridad de Supabase no devolvió avisos inmediatamente tras crear el primer bucket.

El código FastAPI ya soporta `EVIDENCE_BACKEND=supabase` mediante S3 privado con RBAC propio. En Render se registraron solamente endpoint y región, **sin las credenciales**. Mientras falten claves, debe permanecer `EVIDENCE_BACKEND=none` para no anunciar un servicio ficticio.

Para activarlo en **Render Environment**, obtener el par S3 en Supabase Dashboard → Storage → S3 Configuration → Access Keys. Configurar secretos directamente allí:

| Variable | Valor |
|---|---|
| `EVIDENCE_BACKEND` | `supabase` (poner solo tras añadir las credenciales) |
| `EVIDENCE_CONTAINER_NAME` | `s4p-evidence-private` |
| `SUPABASE_S3_ENDPOINT` | `https://klnfxzyccohplnzbdecy.storage.supabase.co/storage/v1/s3` |
| `SUPABASE_S3_REGION` | `us-east-1` |
| `SUPABASE_S3_ACCESS_KEY_ID` | Identificador S3 privado |
| `SUPABASE_S3_SECRET_ACCESS_KEY` | Secreto S3 privado |

No pegar secretos en GitHub, documentos ni chat. Cambiar `EVIDENCE_BACKEND` solo al mismo tiempo que las claves; `/api/readyz` falla cerrado si el bucket no es alcanzable.

**Validación pendiente:** una carga real desde la interfaz, lectura, restricciones entre empresas y eliminación compensatoria, con revisión de logs. La prueba con cliente S3 simulado verifica la compatibilidad del adaptador, pero no la conexión real.

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
- Evidencia: subir, recuperar, validar RBAC/empresa, borrar y comprobar persistencia tras redeploy.
- Finanzas: CI verde + pruebas de negocio con empresa sintética y reversión/auditoría sin datos reales.
- Permanencia: base no caducable, copia externa diaria real, alerta ante fallo y una restauración ensayada.
- Nunca considerar `Live` del servidor como certificación de estas tres capacidades.
