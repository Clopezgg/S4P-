# S4P — Plan maestro de transformación del ERP

## Contexto y decisiones (2026-10-28)
Repositorio origen: `Clopezgg/nexora-group`, rama `main`, SHA de referencia `2ca980446654f3c92e3ddb1e8f55d847ef073968`. Repositorio destino: `Clopezgg/S4P-`. El origen no debe modificarse.

## Principios de conservación
1. Preservar la apariencia SAP Fiori/SAP GUI existente, incluidos los tokens de `frontend/src/design-system`, `frontend/src/sap-gui`, los layouts y el branding.
2. Mantener React/TypeScript/Vite y Python/FastAPI/SQLAlchemy/PostgreSQL/Alembic como línea base de compatibilidad.
3. No convertir operaciones financieras a SQLite/D1 sin pruebas de integridad equivalentes y decisión explícita.
4. Tesorería controla efectivo; los proyectos gestionan presupuestos, compromisos y costos, no saldos propios.
5. `ActiveUIContext` es independiente de `OperationScope`.
6. Todas las operaciones requieren aislamiento multiempresa y, cuando corresponda, por proyecto.
7. Ningún paso de migración puede introducir datos simulados, secretos, credenciales ni saldos ficticios.

## Centros de trabajo
- Inicio ejecutivo: KPIs, alertas, tareas y aprobaciones.
- Proyectos: obras, WBS, cronogramas, presupuestos, avance y contratos.
- Finanzas: tesorería, AP/AR, contabilidad, conciliaciones, cierre y flujo de caja.
- Abastecimiento: solicitudes de compra, órdenes, proveedores y contratos.
- Inventarios: artículos, almacenes, movimientos y costos de consumo.
- Operaciones: equipos, personal, sitio, calidad y seguridad.
- Control: aprobaciones, auditoría, notificaciones y excepciones.
- Administración: empresas, usuarios, roles, permisos y configuraciones.

## Flujo crítico de punta a punta
Solicitud de compra → autorización → orden → recepción → factura con matching → obligación AP → pago mediante tesorería → contabilización GL → conciliación → auditoría.

Garantías requeridas: validaciones de presupuesto y ámbitos, prohibición de duplicados, operaciones atómicas, controles de concurrencia, reversos compensatorios, cierre fiscal, documentación de evidencias, rastreabilidad e idempotencia de pagos.

## Arquitectura objetivo conservadora
- Cloudflare: publicación web y seguridad de borde.
- React/Vite: frontend estático con API `/api` en el mismo origen para evitar errores de sesión en Safari.
- FastAPI: API transaccional en hosting compatible con Python; Cloudflare Workers no reemplaza automáticamente el backend.
- PostgreSQL: persistencia principal, backups y migraciones Alembic.
- Cloudflare R2: archivos y evidencias cuando esté completada una integración real compatible S3.
- GitHub Actions: pruebas, despliegue controlado y rastreabilidad de artefactos.
- Observabilidad: logs, correlación de solicitudes, alertas y health/readiness verificable.

## Puertas de calidad, en orden
### Fase 0 — importar y definir línea base
- [ ] Importar todos los archivos y binarios desde main del origen.
- [ ] Verificar SHA y comparar manifest de archivos; identificar ausencias.
- [ ] Asegurar CI propio y deshabilitar deploy Azure automático para S4P.
- [ ] Baseline: frontend build/typecheck/lint, backend pytest/Ruff, Alembic desde base nueva.

### Fase 1 — estabilidad
- [ ] Reproducir fallos del CI existentes.
- [ ] Revisar vulnerabilidades de dependencias y secretos.
- [ ] Revisar las ramas no fusionadas contra main, sin merge ciego.

### Fase 2 — integridad financiera y seguridad
- [ ] Testear purchase-to-pay con PostgreSQL real.
- [ ] Testear concurrencia y double-submit en pagos e inventario.
- [ ] Validar RBAC/compañía/proyecto, auditoría y reversos.

### Fase 3 — modularización
- [ ] Limitar dependencias entre dominios.
- [ ] Introducir contratos de API tipados y manejo consistente de errores.
- [ ] Deduplicar componentes/servicios con pruebas de regresión.

### Fase 4 — experiencia SAP
- [ ] Inventariar pantallas reales vs incompletas.
- [ ] Reorganizar 8 centros de trabajo sin cambiar marca ni diseño visual.
- [ ] Validar accesibilidad, responsive, tablas, formularios y recorridos E2E.

### Fase 5 — infraestructura
- [ ] Provisionar y probar alojamiento PostgreSQL y FastAPI.
- [ ] Adaptar almacenamiento a R2 y probar evidencias.
- [ ] Publicar frontend en Cloudflare con proxy/API seguro de mismo origen.
- [ ] Configurar secretos y backups, probar restauración.
- [ ] Certificar release mediante CI verde y smoke real autenticado.

## Prohibiciones
- No declarar el ERP listo solo por copiar el repositorio.
- No fusionar PRs con CI rojo.
- No usar el frontend como única evidencia de integridad financiera.
- No borrar ramas o sistemas antiguos antes de verificar rollback.
- No ejecutar operaciones de producción sin respaldos comprobados.

## Estado de ejecución
Plan maestro registrado; la validación de importación, ejecución de pruebas y despliegue quedan pendientes de evidencia real.
