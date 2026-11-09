# Continuidad ejecutada — 2026-11-09

Estado **NO-GO**. Base de esta continuación: main `0b30b27e5dc4c121b3fe918c0a8a4ba43d81fc19`, reconsultado al retomar y antes de publicar. Ver AUD-012 a AUD-015 en DEFECTS.md. Las reparaciones previas de atomicidad, AR/AP, restauración y PWA se conservan.

## Pruebas reales

`backend/tests/test_residential_financial_journey.py`: un proyecto residencial creado por API, raíz + 13 WBS, presupuesto 10.000, caja/banco, remesa 10.000, proveedor, contrato 1.000, plan, factura, aprobación asignada, pago 1.000, recibo oficial, GL, conciliación/desconciliación y reverso. La base local dedicada se crea con todas las migraciones; ningún movimiento se inserta mediante SQL. La fixture solo conecta a localhost y elimina overrides PGHOSTADDR/PGSERVICE.

Negativos: duplicado de factura, replay de remesa y pago, misma clave con payload distinto, pago sin allocation, requester no aprueba su propia solicitud, no se salta workflow pendiente mediante aprobación directa, usuario de empresa ajena no lee factura/PDF, usuario de misma empresa sin proyecto no lee plan ni resumen, Auditor no crea planes ni libera retenciones, segundo reverso rechazado. La revocación del grant legado se prueba con PostgreSQL y doble bootstrap idempotente.

Cuatro pruebas integradas/catalogo/PDF PASS; 56 regresiones de contratos, RBAC multiempresa/proyecto, branding y PDF PASS. Ruff app/tests y git diff --check PASS. Evidencia estructurada: `evidence/continuity-finance-rbac-pdf.json`. CI debe repetirse sobre el SHA nuevo; los seis SUCCESS previos de 0b30b27 no certifican este cambio.

Persistencia: reinicio real del contenedor PostgreSQL, snapshots SQL de conteos/GL idénticos, luego proceso uvicorn nuevo y HTTP real en loopback. Cuatro documentos, ocho líneas, débitos=créditos=13.000, cero documentos desbalanceados, 14 WBS, factura APPROVED y pagado=0; caja 10.000 y banco 0. Login/identity/PDF=200 y PDF tras logout=401. Readiness productiva no se infiere de esta base QA.

PDF: antes 3 páginas para pago contractual, después 2 carta (612×792), contrato e historial presentes, firmas completas y token/QR verificable. Se inspecciona raster del recibo contractual y extracción de texto. Los fixtures sin contrato y branding también pasan. Limitaciones: el contrato queda DRAFT (no se acredita activación/aprobación contractual); datos largos pueden reducir letra. Al regenerar tras reverso el header indica Reversado, pero el bloque contractual desaparece por filtrar allocations reversed_at; pendiente AUD-016 P1 de conservación histórica, no se declara paridad completa de PDF.

## Infraestructura y bloqueo de despliegue

Backend Render sigue LIVE `62258277cf006d875fbb381197ca7dbbcdf09fbd`, autoDeploy=no. ERP real: https://s4p-erp-api.onrender.com/login . Frontend static estaba LIVE 0b30b27 y redirige al backend anterior; no prueba que el backend haya recibido main. No se disparó deploy. /api/version=200 viejo SHA; /api/readyz y /api/backupz=200 ok; /api/auth/me sin sesión=401.

Dockerfile.render mantiene `alembic current --check-heads`, sin upgrade implícito. La consulta SELECT de alembic_version está bloqueada por la allowlist Render vacía. No se cambia allowlist. Main incluye migración 7b2c1af4849c no autorizada en producción. Sigue faltando verificar artefacto anterior retenido y compatibilidad real para rollback. Seis CI verdes por sí solos no desbloquean estas condiciones.

Render PG16 free vence 2026-11-27T23:47:28.940374Z. Supabase PG17.11 mantiene cero tablas ERP; hay 23 objetos en bucket privado de backups (último observado 2026-11-08), pero no clave de descifrado/credenciales puente disponibles para restauración productiva real. No se leen secretos vía SQL ni se cambia DATABASE_URL. El ensayo local PG17 no pudo arrancar: la descarga oficial falla al registrar capa por espacio; no se atribuye ese fallo al ERP. Ninguna migración PG17 exitosa ni base permanente contratada se declara.

## Ruta técnica a base permanente, pendiente autorización específica

1. Confirmar destino PG17 con plan permanente/capacidad y extensiones ERP, acceso privado/SSL, rol runtime sin DDL y rol de migración separado; Supabase vacío todavía no acredita este requisito.
2. Obtener backup cifrado y clave por canal de secretos autorizado, verificar SHA/manifiesto, descifrar a volumen QA independiente y restaurar con owner/ACL adaptados. Registrar RPO con timestamp del backup y RTO medido. No usar como origen la base productiva durante pruebas.
3. Comparar versión Alembic, conteos por empresa, FKs convalidadas, huérfanos, roles/permisos, recibos/tokens/evidencias y doble partida por documento. Ensayar ciclo QA y artefacto de rollback con la revisión exacta.
4. Tras aprobación específica: ventana de escrituras detenidas, backup final verificable, restauración final/paridad, migración explícita aprobada y cambio de conexión. Conservar origen íntegro y credencial anterior durante ventana de rollback. Si hubiera escrituras posteriores al cutover, no volver al origen sin reconciliarlas.
5. Antes de go-live: seis push SUCCESS efectivos del SHA exacto, Safari/WebKit y desktop reales, restore productivo real, RBAC, protección main y gate manual s4p-release-provenance.yml con aprobación humana. No activar flags de aceptación artificiales.

Automatización 6aea875595c48191809b334935400550 revalidada activa. Issue #13 se actualiza solo con cambios verificables. Sin nuevas ramas, merge de PR #11 ni movimientos QA en producción.

## Reparación adicional de texto PDF

Después de 941973b se reprodujo AUD-017: markup de beneficiario interpretado como imagen y error 500. Se escapan todos los párrafos del recibo antes de ReportLab; tres entradas públicas reales (beneficiario/perfil de empresa/pie) se verifican contra un servidor HTTP loopback que debe recibir cero peticiones. No se afirma SSRF externo exitoso. Once pruebas de seguridad PDF, formato, branding y ciclo integrado PASS; el commit adicional exige nuevamente seis push CI del HEAD exacto.
