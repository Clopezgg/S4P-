# CI, Render, rollback y readiness

**NO-GO**. Sin go-live financiero ni CERTIFICADO. Automatización `6aea875595c48191809b334935400550` comprobada `is_enabled=true`; no se pausa.

Seis workflows obligatorios de push del baseline a2ff300...: todos success, jobs no omitidos. Evidencia incluye IDs, SHA, evento, jobs y pasos. El gate se vuelve a evaluar para cada commit enviado a main. No usar el endpoint limitado a eventos PR para concluir que no hay CI de push.

Render backend `srv-dbh8ihec6qcc73em0ho0`: main, autoDeploy=no, Dockerfile.render. Deploy live leído `dep-dbi55c8ae00c73b8s2qg`, SHA `62258277cf006d875fbb381197ca7dbbcdf09fbd`; coincide con /api/version. /api/readyz=200 ok, /api/backupz=200 ok, auth/me sin sesión=401. Los dos primeros requests tras cold start agotaron 25s; repetir después devolvió salud correcta. La búsqueda de logs request de estos paths devolvió vacío; no se inventan logs.

Dockerfile.render mantiene `alembic current --check-heads && ... uvicorn`, sin upgrade implícito; regresión dedicada lo exige. La nueva aplicación puede negarse a arrancar si producción no está en head: readyz de la versión vieja no demuestra compatibilidad con el nuevo esquema. La lectura SQL de Alembic de producción está bloqueada por red.

No se dispara despliegue hasta contar con seis push verdes del SHA vigente, salud previa, verificación Alembic read-only, y rollback verificado. Existen deploys históricos deactivated, pero su listado no prueba que un artefacto retenido siga siendo desplegable ni compatibilidad DB. Antes de un despliegue controlado: registrar artefacto anterior y compatibilidad, mantener tráfico previo hasta readiness y verificar nuevo SHA mediante /api/version; si falla, recuperar versión previa y volver a comprobar salud/auth/logs. Rollback de aplicación no revierte datos, migraciones ni archivos externos.

Gates de liberación pendientes: restauración cifrada real, DB permanente, ciclo financiero residencial completo en QA con persistencia tras reinicio, RBAC por acción y acceso cruzado, Safari, seis CI del HEAD final, protección main, simulacro rollback y aprobación humana. `s4p-release-provenance.yml` existe y requiere variables de aceptación DB/restore/finanzas y environment production; su existencia no demuestra aprobación ni ejecución. No se activan banderas para fingir certificación.
