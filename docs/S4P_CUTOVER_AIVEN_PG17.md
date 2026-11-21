# S4P: procedimiento seguro Render PG16 a Aiven PG17

Estado actual: se escribió y versionó una herramienta de clonación con controles estrictos. La clonación de datos reales NO se ha ejecutado ni se ha realizado un cambio de conexión del ERP.

## Alternativas comprobadas

- Destino económico preferido: servicio existente Aiven free-1-1gb PostgreSQL 17, DigitalOcean NYC. Su plan no caduca por tiempo, pero tiene únicamente 1 GB de disco, un solo nodo y carece de HA adecuada para un ERP financiero crítico.
- Supabase Free: opción de contingencia, pero los proyectos gratuitos pueden pausarse tras un período de inactividad y tienen límites más bajos; el proyecto actual también almacena los respaldos privados.
- Neon Free: la capacidad de cómputo se suspende sin actividad; útil para pruebas o desarrollo, no garantiza operación continua.
- Producción con alta disponibilidad: exigir presupuesto/aprobación para un plan administrado con backups y objetivos RPO/RTO, ya sea Aiven pago, Render PostgreSQL pago o Supabase Pro.

Fuentes oficiales: https://aiven.io/docs/products/postgresql/concepts/pg-free-tier , https://aiven.io/pricing/postgresql , https://supabase.com/pricing , https://neon.com/pricing , https://render.com/docs/free

## Fuente y destino

El PostgreSQL 16 gratuito de Render expira el 27 de noviembre de 2026 a las 23:47 UTC. Conservar bloqueadas sus conexiones externas. La fuente de verdad sigue siendo Render hasta que se cumplan todas las pruebas. Aiven s4p-postgres-free está RUNNING y protegido contra eliminación accidental, pero tiene cero tablas de negocio a la última consulta.

Aiven tiene IP allowlist globalmente abierto a 0.0.0.0/0 y ::/0. Es necesario restringirlo antes de cargar datos; si el servidor Render no dispone de IP de salida fija, preparar una ruta privada y autorizada para la transferencia sin abrir el origen.

## Requisitos para clonar

La herramienta está en backend/scripts/pg16_to_aiven_pg17.py, dentro de la imagen principal Dockerfile.render, que dispone de cliente PostgreSQL 17. No exige copiar ni mostrar secretos en chat. Ejecutar dentro de la red privada autorizada de Render, con variables protegidas, no en GitHub público:

- DATABASE_URL: URL interna actual del origen Render, solo se utiliza para lectura.
- S4P_AIVEN_TARGET_DATABASE_URL: URL de Aiven defaultdb con sslmode=verify-full.
- S4P_AIVEN_EXPECTED_HOST: hostname exacto del servicio Aiven.
- S4P_AIVEN_CA_FILE: ruta local a un certificado CA del proyecto Aiven, instalado fuera del repositorio.
- S4P_MIGRATION_BACKUP_VERIFIED=1, únicamente tras restauración comprobada de un backup REAL.
- S4P_AIVEN_IP_ALLOWLIST_RESTRICTED=1, únicamente tras comprobar el filtro IP en Aiven.
- S4P_MIGRATION_WRITE_FREEZE_CONFIRMED=1, únicamente después de detener escrituras de negocio durante el cambio.

La herramienta NO comprueba por su cuenta la verdad de esas tres certificaciones operativas; deben respaldarse con registros de un operador autorizado. No introducir valores reales de secretos en argumentos, workflows, logs o issues.

Comando de clonación dentro de Render, una vez atendidos los requisitos:

    cd /app
    python scripts/pg16_to_aiven_pg17.py --clone-to-empty-target

La herramienta se niega si cambia la identidad del origen o destino, falta verificación TLS, el destino no está vacío, la versión no es PG16→PG17, faltan roles/datos o el GL no cuadra. Usa pg_dump -Fc en un directorio 0700, compara huellas fila por fila, restaura en Aiven bajo transacción, compara recuentos, contenido, Alembic y restricciones, y deja al origen intacto. No cambia DATABASE_URL, no despliega y no borra los datos del origen.

## Pruebas reproducibles, sin producción

El workflow S4P PG16 to PG17 isolated migration parity drill crea PostgreSQL 16 y 17 efímeros en CI, genera el esquema real mediante Alembic, carga una compañía, usuarios, roles, una remesa y los asientos por los servicios del ERP, crea un backup real de laboratorio, lo restaura en PG17 y compara el contenido completo de cada tabla, integridad y Alembic. Esto valida compatibilidad técnica, pero NO certifica la capacidad de restaurar el backup de producción.

## Condiciones obligatorias para habilitar el ERP financiero

1. Respaldos cifrados frescos demostrados y recuperación del último backup REAL ensayada en PostgreSQL aislado, con evidencias y tiempos de restauración.
2. Restauración íntegra PG16→PG17 con todos los registros, usuarios, permisos, compañías, facturas, remesas, asientos, movimientos, evidencias y comprobantes.
3. Cuenta de usuario QA aislada, pruebas de permisos entre compañías, procesos AP/AR/tesorería, reversión y exportación; navegador móvil y escritorio.
4. Seis CI obligatorios success en el mismo SHA, rollback ensayado, main protegido y aprobación independiente del entorno production.
5. Solo después cambiar DATABASE_URL en Render mediante secretos y desplegar el backend exacto; comprobar healthz/readyz/backupz/version y la persistencia de datos tras reinicio.
6. Conservar la base Render original sin nuevas escrituras como rollback hasta aceptación definitiva; NO volver a ella tras aceptar operaciones nuevas en Aiven sin reconciliar.

Si faltan credenciales privadas o acceso autorizado para ejecutar la clonación, registrar NO-GO; nunca marcar como migrado o certificado. No habilitar cobros/gastos reales con la base caducable.
