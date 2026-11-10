# Recuperación y despliegue controlado autorizados — 2026-11-10

El usuario autorizó expresamente la migración productiva 7b2c1af4849c tras
restauración y rollback verificados. Esa autorización no sustituye las pruebas
ni constituye go-live financiero o certificación corporativa.

## Vía alternativa sin extraer secretos

La documentación actual de Render permite `fromService.envVarKey` de un
servicio existente fuera del Blueprint. `render-recovery.yaml` define SOLO un
servicio gratuito temporal, sin adoptar ni alterar backend, DB o secretos
existentes. Las referencias se resuelven dentro de Render. No se crea otra
PostgreSQL gestionada, evitando el límite de una gratuita por workspace.

`Dockerfile.recovery` ejecuta un cluster PG17 independiente, exclusivamente
loopback y temporal. No sirve ERP ni permite descargar datos restaurados. El
cluster se destruye al terminar. `/healthz` indica proceso disponible;
`/status` informa resultado SANITIZADO. LIVE no equivale a restore aprobado.
No hay endpoint HTTP de comandos, SQL, migración o reversión.

`preflight` (por defecto): SELECT en producción por TLS, comprueba revisión,
identidad, FKs y GL; descarga/descifra el backup real mediante el puente
existente y restaura únicamente en la base vacía local. Comprueba integridad
y ensaya upgrade/downgrade de esquema, comparando todo el contenido de todas
las tablas públicas salvo el registro Alembic. Los hashes quedan en memoria,
nunca en logs o Git. Se publica fecha/edad del backup y tiempo de recuperación;
la edad del backup no garantiza por sí sola un RPO contractual.

Después se descarga el código S4P de la versión previa fijada por SHA6225827,
se verifica su gate Alembic sobre la revisión restaurada eb8ce8e18b2d y se
arranca su API únicamente en loopback contra la copia recuperada. Se exigen
readyz=ok, version con ese SHA y auth/me sin sesión=401; el proceso se termina
antes de borrar el cluster. No se afirma que esto sea un rollback ejecutado
en producción ni prueba de disponibilidad de todos los artefactos de Render.

Primer preflight remoto44b7738: producción leyó revisión eb8ce8e18b2d y backup
real2026-11-10T07:06:33Z; falló después con TypeError, sin escrituras
productivas. El cluster temporal ahora exige UTF8 explícito. El arranque real
del código anterior y su gate/readyz/version/401 pasan también en QA local.

`migrate`/`rollback`: requieren selección explícita por configuración del
servicio temporal, `S4P_APPROVE_SCHEMA_CHANGE=7b2c1af4849c` y
`S4P_APPROVED_MAIN_SHA` igual al SHA real de Render. Cada operación repite
restore/ensayo antes de escribir. Únicamente admite eb8ce8e18b2d ↔
7b2c1af4849c y el host/nombre de la DB concreta autorizada. La transacción
SERIALIZABLE incluye lock, DDL, actualización Alembic, comparación de contenido
y checks; lock_timeout=5s y statement_timeout=30s. El downgrade rechaza
valores largos, sin truncarlos. Un fallo revierte DDL y versión juntos.

El soporte de conexión suministrada en `alembic/env.py` es el patrón normal
de Alembic para una transacción externa; no hace stamp ni omite migraciones.
Dockerfile.render conserva `alembic current --check-heads`, sin upgrade.

## Gates de ejecución

1. Revisar plan: añadir solo servicio gratuito; ninguna modificación de los
   recursos productivos ni secretos manuales. No aprobar plan con coste nuevo
   o adopción/cambios de recursos existentes.
2. Ejecutar preflight y exigir status=success, restoreVerified=true,
   rollbackRehearsed=true y preservación de todas las filas. Inspeccionar la
   revisión real y estados existentes; un fallo bloquea migración.
3. Confirmar seis workflows push del HEAD vigente, diez jobs y pasos críticos.
4. Ejecutar migración autorizada; verificar revisión y filas preservadas.
5. Trigger backend, esperar LIVE, confirmar SHA/version/readyz/backupz/auth401,
   login/assets/logs. Si falla antes de relevo, preservar instancia anterior;
   ensayar/aplicar reversión de esquema sin pérdida antes de reiniciar la
   aplicación anterior, cuya revisión head es eb8ce8e18b2d.
6. Devolver servicio temporal a preflight y conservar solo informe saneado.

Siguen separados los gates de certificación: DB permanente antes del
2026-11-27, protección main, aprobación humana corporativa, aceptación
funcional pendiente y conservación histórica del PDF tras reverso (AUD-016).

Referencias verificadas: https://render.com/docs/blueprint-spec.md,
https://render.com/docs/private-network.md, https://render.com/docs/free.md y
https://render.com/docs/rollbacks.md.
