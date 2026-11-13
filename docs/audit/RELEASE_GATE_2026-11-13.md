# Gate de lanzamiento: continuidad 2026-11-13

Estado financiero **NO-GO**. Este documento no certifica un despliegue nuevo.

## Defecto reproducido y reparación

AUD-026 P0: `s4p-release-provenance.yml` comprobaba tres variables booleanas y el SHA desplegado, pero no exigía protección real de main, revisión independiente configurada, seis workflows push del SHA exacto ni jobs/pasos críticos efectivos. Una aprobación antigua podía permanecer marcada y el SHA de una ejecución manual podía quedar atrás de main mientras esperaba revisión.

Se añade `backend/scripts/release_provenance.py`, de solo lectura. Verifica main al inicio y al final, protección clásica estricta con diez checks requeridos y sin force push/borrado, environment production con reviewer y prevent_self_review, seis workflows push del HEAD, su intento más reciente, diez jobs y pasos críticos exitosos. Pagina respuestas e impide aceptar checks de PR, SHA distinto, jobs omitidos o intentos antiguos. El workflow ejecuta esta verificación antes y después de las comprobaciones HTTP; mantiene las tres aceptaciones corporativas y la revisión del entorno. No configura protección, no despliega y no escribe datos.

Las reglas de protección mediante rulesets no se certifican automáticamente: se exige la protección clásica explícita preparada para este repositorio. Si se adopta otra política, debe revisarse y soportarse antes de abrir el gate; un 403 o una política no verificable no se convierte en aprobación.

Verificación local inicial: 24 tests de decisión PASS y Ruff PASS. Son respuestas de GitHub controladas para probar el guard; no son pruebas productivas. Ejecución real contra main `62426b786c2deb4921d17597001a0879d8e2bb60`: exit 1, `Release blocked: Main has no active protection`.

## Acceso administrativo pendiente

El token estándar de Actions no garantiza lectura de Administration. El gate admite el secret de entorno `S4P_RELEASE_GOVERNANCE_TOKEN`: token fino, limitado a este repositorio, Administration/read, Actions/read y Contents/read. No necesita permiso de escritura ni se imprime. Debe provisionarse por el propietario con acceso efectivo, sin pegarlo en chat/repositorio. Si no existe se intenta github.token; cualquier denegación mantiene el gate cerrado. No se ha creado ni cambiado ningún secreto durante esta reparación.

El propietario debe configurar la protección de main y un reviewer humano independiente de quien inicia la liberación; marcar las tres aceptaciones solo tras evidencia vigente. La revisión necesita una persona disponible diferente del iniciador si prevent_self_review está activo. El script puede ejecutarse sin mutar infraestructura:

```sh
python3 backend/scripts/release_provenance.py --expected-sha SHA_COMPLETO --repository Clopezgg/S4P-
```

Usa GH_TOKEN/GITHUB_TOKEN desde un almacén seguro, nunca un argumento. El SHA debe ser el HEAD actual, con sus seis CI push completados. Cada nuevo commit requiere CI propio y revalidación de salud/backup/rollback antes de desplegar.

## Bloqueos externos revalidados

Render MCP continúa `UNAUTHORIZED`, exige reconexión. No existe RENDER_API_KEY en el entorno ni CLI autenticado disponible como alternativa. No se reutilizan tokens internos ni se evaden permisos. No se consultaron logs/métricas ni se activó otro deploy.

La propuesta versionada `render-permanent-db.yaml` conserva la instancia actual sin cambiar DATABASE_URL; el último plan alcanzado falló `payment_removed`. No se ha contratado nada. Supabase PG17 existente es una alternativa de destino, todavía sin tablas ERP al último control: requiere conexión nativa segura, aislamiento y ensayo de paridad, además de aprobación de cutover; el plan gratuito puede pausarse y no acredita disponibilidad permanente.

Los timeouts públicos observados se investigan por endpoint separando liveness, versión, readiness, backup y estáticos. Sin logs/métricas no se atribuye causa ni se cambia pool, timeout, plan o almacenamiento a ciegas. El gate sigue cerrado hasta resolver disponibilidad sostenida, base permanente, gobernanza y aceptación.
