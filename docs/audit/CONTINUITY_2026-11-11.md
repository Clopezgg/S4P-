# Continuidad — 2026-11-11

## Estado acreditado al comenzar

Main local/remoto: `8d02c680a1e46cb646b245e3e9ff263675bfc0dc`, sin cambios concurrentes. Backend Render `srv-dbh8ihec6qcc73em0ho0`: deploy `dep-dbpj1hui0phs73ab6h2g`, LIVE con ese SHA. La ejecución anterior acreditó seis workflows push SUCCESS, restauración de backup productivo cifrado en PostgreSQL independiente, migración aprobada `7b2c1af4849c`, login/logout reales y 12 verificaciones públicas de login en Chromium/Firefox/WebKit. Esas pruebas corresponden a ese SHA, no sustituyen las del nuevo HEAD.

## Reparaciones de comprobantes

**AUD-016 P1:** la primera emisión guarda un snapshot JSONB versionado de historia de cuotas, importes Decimal serializados como texto, corte, categoría, referencia, observaciones y resumen contractual. La reimpresión usa exclusivamente ese snapshot aunque las allocations hayan sido revertidas. También respeta fecha, código de verificación, moneda, importe, método, banco y nombre del proyecto de la emisión original. Los recibos anteriores sin detalle JSON conservan sus totales originales y muestran «Detalle histórico de cuotas no registrado»; no se fabrica una historia con saldos actuales.

**AUD-023 P1:** el QR resolvía un estado contable almacenado y podía seguir mostrando POSTED tras el reverso. Reimprimir también sobrescribía empresa, beneficiario, fecha y código públicos. Ahora el endpoint consulta el estado vigente del documento, sin escribir desde la verificación pública, y toma identidad/importes de VoucherIssuance cuando existe. El token y su metadata original no se reescriben.

## Esquema y reversibilidad

Migración nueva `dae6224cb8be`, padre `7b2c1af4849c`: agrega únicamente `voucher_issuances.contract_context_snapshot JSONB NULL`, sin backfill. Downgrade de expansión conserva la columna y datos históricos: la aplicación anterior ignora el campo adicional. Upgrade es idempotente. El procedimiento controlado se actualiza al nuevo par de revisiones y pin de aplicación previa 8d02. La huella compara todas las filas e incluye snapshots no nulos; normaliza solo el campo nuevo cuando es NULL para comparar con el esquema anterior. No cambia DATABASE_URL, secretos o allowlists. Dockerfile.render conserva `alembic current --check-heads` sin upgrade implícito.

## Pruebas locales reales

PostgreSQL aislado local: **9 PASS** en test_voucher_pdf_format, test_residential_financial_journey, test_company_branding_voucher y test_release_maintenance, 18.38 segundos. El ciclo usa APIs para empresa/proyecto/13 WBS/presupuesto/remesa/proveedor/contrato/factura/aprobación/pago/PDF/GL/conciliación/reverso y comprueba persistencia tras reiniciar la aplicación. Se añadió reimpresión contractual después del reverso, compatibilidad legacy y rollback/re-upgrade con snapshot no nulo. La regresión QR falla contra la implementación original (1 FAILED) y pasa con la reparación. No hubo movimientos financieros QA en producción.

## Gates pendientes y restricciones

Render confirma PG16 Free disponible, expiración `2026-11-27T23:47:28.940374Z`, ingreso externo cerrado. `render-permanent-db.yaml` propone adoptar exclusivamente la instancia existente, plan `0.1c-256mb`, almacenamiento explícito 1 GB, autoscaling deshabilitado, mismos nombres/región/PG16/allowlist. Validó contra el JSON Schema actual; falta revisión del plan Render y aprobación expresa del coste recurrente antes de aplicar. No se ha contratado ni migrado producción por esta propuesta.

La aprobación contractual sigue sin transición demostrada desde DRAFT: la aprobación de la factura no acredita la del contrato. GitHub devuelve 403 al consultar protección de main; rulesets vacío y environment production ausente en la inspección previa. No se atribuyen permisos administrativos que la integración no tiene ni se escriben variables de aceptación para fingir certificación.

El nuevo HEAD necesita sus seis workflows push efectivos y restauración/rehearsal actual antes del despliegue controlado. Estado financiero **NO-GO** mientras falten DB permanente, gobernanza y aceptación humana documentada. Los resultados posteriores de CI/Render deben registrarse con SHA exacto en issue #13 y evidencia; este documento no anticipa un despliegue.

## Recuperación de esquema reciente

El primer preflight ad4dbc4 se detuvo sin mutación productiva: seleccionó el backup del 10 de noviembre anterior al upgrade7b. Se añade captura cifrada explícita del esquema actual antes del drill, usando pg_dump de lectura y el puente privado existente; el intervalo del scheduler permanece igual y los archivos anteriores no se sobrescriben ni eliminan. Prueba unitaria separada valida force/intervalo/inmutabilidad; no constituye evidencia de backup real, que se exige al ejecutar el preflight en Render. Render rechazó además la planificación de DB permanente con `payment_removed`; no hay plan aprobable mientras ese bloqueo del proveedor continúe.

## Dependencias y PWA

Audit npm inicial: seis moderate y dos low, cero high/critical. Vitest/UI 5.1.0 elimina la cadena vulnerable de mocker; vite-plugin-pwa2.0.0 conserva compatibilidad declarada con Vite7/Node24. Workbox7.4.1 conserva glob11 afectado: override limitado a `workbox-build.glob`14.0.2, cuya llamada globSync(cwd/follow/ignore) fue revisada y probada con build real. No se usó el downgrade PWA1.1.0 sugerido por npm. Resultado: **cero moderate/high/critical**, cuatro avisos low en una misma cadena de deepmerge; la versión publicada más reciente4.3.1 sigue afectada, no se declara remediada.

Typecheck/lint PASS, **79 archivos/278 tests PASS**, build productivo PASS. El guard del artefacto confirma un solo manifiesto standalone, metadatos/iconos precacheados y ausencia de HTML/JS/CSS/APIs en precache. Se mantienen NetworkOnly para API y SAP escritorio. El nuevo SHA requiere repetir los seis CI y recorridos browser completos; una actualización local de dependencias no acredita móvil autenticado productivo.

Prueba adicional: **9 PASS en PostgreSQL17.11 independiente local**, 18.87s, con trazabilidad de123 requests/49 combinaciones método-ruta-estado. Se conservan401/403/409/422 negativos; no datos productivos. La restauración REAL del backup2026-11-11T05:32:37Z en Render PG17 pasó integridad y rollback de aplicación previa8d02 en49.649s, temporal eliminado. Backup real sin asientos/recibos: no se usa para afirmar validación financiera sobre datos ausentes. Intentos reales de configurar protección main y environment production: ambos403 Resource not accessible by integration; no hubo cambios administrativos.

## AUD-024 P0 — fuga de proyectos en búsqueda documental

Reproducido contra implementación anterior: usuario Finance Manager de la empresa, sin proyecto asignado, encuentra contrato/factura por número aunque no puede abrirlos. Segundo caso: asiento GENERAL con líneas de un proyecto restringido aparece por búsqueda aunque GET del asiento devuelve403. Ambos fallan en regresiones reales separadas.

La ruta exige ahora los project_ids de `accounting.journal_entry:read`. El servicio aplica empresa y proyecto **antes de LIMIT25** en AP/AR/PO/contratos/GL; vouchers/remesas heredan el alcance de AccountingDocument y pagos de SupplierInvoice/AccountingDocument. Un EXISTS correlacionado excluye cualquier asiento con líneas de proyectos no autorizados, incluso si header.project_id es NULL. Las filas GENERAL/CENTRAL legítimas se conservan. No cambia catálogos ni amplía permisos.

Regresiones reales verifican: contrato/factura y referencias de pago/QR/asiento ocultos a usuario sin asignación; pago visible al usuario asignado; remesa general visible; empresa ajena sin resultados; encabezado general con líneas restringidas invisible; proyecto permitido no queda oculto tras26 contratos de otro proyecto que coinciden con la búsqueda. Pruebas de alcance/evidencia existentes se conservan. El nuevo HEAD requiere seis CI push íntegros antes de cualquier actualización productiva.

## Aprobación contractual y segregación operativa

Se implementa envío DRAFT/REJECTED→REVIEW y decisión ACTIVE/REJECTED en el inbox real. El aprobador debe ser activo, distinto del solicitante, con permiso de decisión y acceso vigente a empresa/proyecto. El lock del contrato serializa envíos; la transacción incluye solicitud, estado, notificaciones y auditoría. Rechazo permite un nuevo envío, sin borrar decisiones anteriores. El inbox filtra los proyectos actuales; revocar acceso oculta la solicitud y bloquea la decisión. Ahora `workflow.*` hereda OWN/ANY de empresa para project_scope mediante la normalización RBAC existente. No se amplían company scopes.

**Cierre del bypass DRAFT:** la factura puede prepararse en borrador; contabilizarla o pagar exige contrato ACTIVE, también para facturas aprobadas por versiones anteriores. REVIEW/REJECTED impiden nuevas obligaciones y pagos. El resumen contractual emite payableNow=false y motivo antes de aprobación. No se activan contratos legacy automáticamente: los existentes deben pasar por dos actores reales. Las fixtures de pago ahora recorren aprobación real por API y conservan la sesión original; se retiraron activaciones directas SQL de las fixtures modificadas. Se preservan las aserciones financieras; presupuesto disponible refleja el compromiso de1.5m tras aprobación (2m→0.5m), mientras caja conserva2m y el anticipo permanece ASSET, no costo.

UI: Contratos de ejecución ofrece Enviar a aprobación, excluye al solicitante, muestra errores backend, cambia estado y comparte inbox. La bandeja identifica contrato/tercero, moneda real y nombre del solicitante. El E2E usa cookies/DB reales: solicitante y Finance Manager distintos, aprobación por UI, persistencia ACTIVE y formulario360/390/430/768; ejecutado en bundle productivo Chromium/WebKit. También se actualizó la precondición del E2E de cuota vencida con aprobación real independiente; todas sus aserciones de Pagar/Liquidar permanecen.

Nueva migración **32c92271c634** sobre dae6224cb8be amplía la constraint de estados contractuales (REVIEW/REJECTED). No se reescribe la migración de snapshot ya versionada. El release controlado pasa de7b2c1af4849c a32c92271c634, atravesando ambas revisiones. Ambos downgrades conservan columnas/estados nuevos para no destruir historia; la aplicación previa8d02 se ensaya con versión Alembic7b y expansión retenida. El arranque productivo continúa read-only `current --check-heads`.

Regresiones nuevas: concurrencia real de dos sesiones crea una sola solicitud; un trigger temporal PostgreSQL inyecta fallo de auditoría y exige rollback de estado contractual y solicitud, seguido de reintento exitoso; contrato DRAFT bloquea posting y pago legacy sin mover caja. El ciclo residencial ahora incluye rechazo/reenvío/aprobación contractual antes de factura y mantiene los13 WBS, remesa, GL, conciliación y reversión. Typecheck/lint/build y79archivos/279tests frontend PASS; suites financieras y recorridos se registran por entorno, sin sumar ejecuciones repetidas como casos distintos.

CI3d7c596 falló por la expectativa fija7b en test_ar_status_migration tras agregar migraciones posteriores. La prueba ahora exige el HEAD Alembic real y sigue comprobando colección parcial persistida, status32 y rechazo del downgrade truncador. No se elimina ninguna aserción de integridad. El nuevo HEAD debe completar seis push SUCCESS con jobs efectivos; resultados de SHAs anteriores no certifican este cambio.

## AUD-025 P0 — entidades ORM obsoletas después de FOR UPDATE

Reproducción en PostgreSQL real con5sesiones independientes y barrera: cada sesión carga la factura antes de pedir el lock, como hacen los resolutores de permiso/ruta. Código anterior: **5 pagos aceptados de la misma deuda** y **5 cobros aceptados de la misma factura**, aunque el saldo ORM final ocultaba el exceso. Son datos QA locales, nunca producción.

AP, AR, repositorio de aprobaciones y locks contractuales ahora usan `populate_existing=True` al adquirir FOR UPDATE, recargando la fila persistida después de esperar. Las regresiones conservan referencias ORM obsoletas deliberadamente; exigen exactamente1éxito y4rechazos, saldo correcto y un solo cobro. También se fortaleció la concurrencia de envíos contractuales con una entidad precargada. No se amplía el pool ni se cambia aislamiento para ocultar la carrera.

**13regresiones finales PASS** en DB QA separada: carreras AP/AR, aprobación contractual/legacy/fallo real de auditoría/concurrencia, ciclo residencial con revocación/restitución de proyecto, AR upgrade/downgrade truncador, anticipo con compromiso presupuestario correcto y procedimiento de recuperación. El ciclo conserva una cookie jar autenticada por persona y verifica identidad al cambiar de actor: evita reautenticar decenas de veces desde el mismo cliente sin desactivar el rate limit. El límite de login permanece intacto. La suite completa local anterior sigue en ejecución y el CI del nuevo HEAD será la evidencia definitiva; no se atribuye SUCCESS de commits previos.

Continuidad concurrente: se detectó main6e8d7c4 durante la preparación. Ese commit corrige la misma expectativa AR consultando `alembic heads` y exigiendo un único head. Se conservó íntegro mediante fast-forward; nuestra edición redundante se retiró. Su prueba pasó además sobre el esquema nuevo32c92271c634 (1PASS/8.10s). No se repite PR11 ni se crean ramas ni se sobrescribe el trabajo concurrente.
