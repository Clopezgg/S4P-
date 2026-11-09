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


## Restauración independiente PG16 → PG17 conseguida

La limitación inicial de espacio se resolvió sin tocar producción: otro contenedor reutiliza la base Debian existente e instala PostgreSQL 17.11 desde PGDG oficial. Origen QA local en 5432; destino independiente, solo loopback, 5433. El origen no cambió de conexión ni versión. Se generó pg_dump custom del ciclo residencial real, se cifró/descifró con AES-256-GCM mediante `scripts/s4p_backup.py` y clave aleatoria mantenida solo en memoria; el dump descifrado coincide byte por byte y se restauró con `--single-transaction --exit-on-error --no-owner --no-acl`.

Paridad inicial: 112 tablas con conteos iguales, cero FKs sin validar, cero documentos GL desbalanceados y Alembic 7b2c1af4849c. Paridad adicional de contenido: 18 tablas críticas completas y campos inmutables de voucher_verifications; se excluyen document_status/updated_at del token, que se actualizan al regenerar el PDF reversado. No se excluyen importes, identidades, grants ni tokens. Sesiones/último login/audit pueden variar al probar la nueva API.

API real contra PG17 restaurado: login/auth/me/PDF=200, PDF sin sesión=401, QR válido, factura APPROVED/pagado=0, caja 10.000 y banco 0, recibo 2 páginas carta. Chromium y WebKit autenticados: 30 comprobaciones de ruta/viewport (inicio/proyectos/tesorería × 360/390/430/768/1440 × dos motores), cero overflow y cero pageerror. La primera configuración local con Origin incorrecto fue rechazada 403 por CSRF; se corrigió FRONTEND_URL solo en QA. Se esperó a finalizar requests entre navegaciones para no confundir cancelaciones WebKit con fallos de negocio. Sin mock de API.

AUD-018 P1 reparado: Finance Manager carecía de `project:read`, de modo que el selector/listado devolvía 403 incluso con UserProjectAccess asignado. Se añade lectura OWN, sin crear/editar proyectos. Regresión API con proyecto asignado visible, sin asignación lista vacía y empresa ajena 403; 24 regresiones pasan.

Evidencia: pg17-qa-restore.json, pg17-critical-content-parity.json, pg17-restored-http.json, pg17-restored-browser.json y finance-project-read-regressions.json. El tiempo medido de dump/cifrado/restauración/paridad es un ensayo QA (ver JSON), no RTO/RPO productivos. **No se restauró un backup de Supabase/producción ni se contrató DB permanente.** Esto demuestra compatibilidad de estos datos QA en PG17, no un cutover autorizado.

Última revalidación externa: 25 objetos privados de backup (más reciente 2026-11-09 08:05:14 UTC); Supabase PG17.11 sin tablas ERP. Frontend LIVE 9f746a41b4a85f83dfe8c7e09661f858f8f55c6e antes del commit de esta evidencia, backend LIVE antiguo 62258277. Dos HTTP timeouts iniciales; en repetición readyz/version/backupz=200, auth/me=401, login/CSS/JS=200. El JS static redirige al backend anterior. Protección main sigue 403 por integración; logs request solicitados vacíos. No hay deploy backend ni modificación de allowlist, secretos o DATABASE_URL productivos.

El guard de secretos de 2320bac detectó cuatro falsos positivos generic-api-key al asociar hashes MD5 calculados a nombres user_company_access/user_project_access. Se retiran los hashes crudos del JSON publicado y se conserva igualdad verificada por tabla; no eran claves. No se altera la configuración ni se excluye archivo/regla del guard. El nuevo SHA requiere sus seis CI.
