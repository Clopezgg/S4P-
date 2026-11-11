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
