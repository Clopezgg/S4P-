# Obra principal, trabajos y gastos separados

## Comportamiento solicitado

Casa residencial es la obra principal. Verjas, Cerco perimetral, Techo, Acabados y Detalles pueden crearse como trabajos de esa obra. Todos los gastos de Casa suma gastos directos y trabajos explícitamente vinculados; Otros permanece independiente. Seleccionar un trabajo muestra solo su detalle. No se clasifica ni vincula un proyecto por su nombre.

Nuevo proyecto abre el alta sencilla (nombre y obra principal opcional) y lleva al inicio operativo. El asistente anterior conserva sus pasos, fases, presupuesto y contratos en Configuración avanzada. La plantilla residencial sigue disponible de forma opcional.

El inicio de proyecto muestra Registrar gasto, Registrar remesa, Todos los gastos, total y trabajos. Los indicadores comerciales del cockpit siguen en Opciones avanzadas. Un proyecto en planificación debe activarse mediante la transición real autorizada; no se activan proyectos implícitamente al gastar. Si faltan cuentas o permisos se explica el requisito. La acción contextual fija el proyecto en el formulario y también funciona desde Crear en móvil.

## Trazabilidad y reglas

- `Project.parent_project_id`: obra principal opcional, misma empresa y moneda; solo dos niveles. Validación de ciclos, autorreferencia y trabajos anidados. Ediciones serializadas por empresa y refresco de entidad; prueba concurrente de vínculos opuestos exige un éxito y un rechazo.
- FK compuesta de proyectos `(parent_project_id, company_id)` y remesas `(attributed_project_id, company_id)` contra `(projects.id, projects.company_id)`. Índices de ambas referencias y check de autorreferencia.
- `GET /api/projects/{id}/spending`: lectura real de GL y relaciones persistidas. Filtra empresa/proyectos autorizados antes de sumar/paginar, sin heredar permisos por ser padre. Gastos = débitos menos créditos de cuentas EXPENSE, documentos POSTED/REVERSED, misma dimensión de proyecto. Original y reverso se compensan; sin doble conteo. Paginación25, máximo100, total íntegro independiente de página.
- Remesas: referencia documental opcional `attributed_project_id`, validada antes del posting y registrada en auditoría. El GL permanece CENTRAL, con project_id NULL; caja/banco pertenece a Tesorería. La referencia no crea caja ni saldo en Project. Solo se suman remesas POSTED identificadas para miembros autorizados de la obra y en su moneda; una remesa revertida deja de sumar. Remesas antiguas sin referencia no se atribuyen retrospectivamente.
- Scope de gasto PROJECT se envía por una acción explícita; seleccionar contexto UI por sí solo no cambia el alcance de otras operaciones. Formularios y backend conservan permisos, idempotencia, control contractual, edición protegida y auditoría atómica.
- Los vínculos pueden editarse explícitamente en Opciones avanzadas con project:update, permiso de lectura de la obra destino y auditoría antes/después. No se modifican GL, comprobantes ni movimientos históricos al organizar proyectos.

## Datos y despliegue

Alembic `9083ca4ebf44`, padre `32c92271c634`: expansión nullable, sin backfill de clasificación, sin importes ni movimientos nuevos. Downgrade conserva columnas/vínculos; re-upgrade acepta el esquema retenido. Dockerfile.render mantiene `alembic current --check-heads` y ningún upgrade implícito.

Helper de recuperación revisado: origen32, destino9083, aplicación previa62426b7. Huella de filas ignora únicamente los nuevos campos cuando son NULL; los vínculos no nulos forman parte de la huella. Cualquier migración productiva exige CI del nuevo SHA, backup real fresco, restauración independiente, ensayo de rollback y comprobaciones de salud; el código del helper no constituye prueba de ejecución productiva.

## Evidencia local

PostgreSQL real: pruebas de agregación Casa/trabajos/Otros, remesa idempotente CENTRAL, reversos, empresa ajena, trabajos no asignados, validación de FK, ciclos y concurrencia. Ensayo Alembic real conserva filas existentes sin asignación, vínculos nuevos tras downgrade y huellas tras re-upgrade. Suite dirigida43PASS; revisión posterior de jerarquía/recuperación11PASS; suite posterior con residencial/reversos/ciclo de vida28PASS (hay solapamiento, no se suman).

Frontend279PASS, typecheck/lint/build y guard PWA PASS. Navegador sobre bundle de producción, backend y PostgreSQL QA: Chromium/Firefox/WebKit, 360/390/430/768px y escritorio SAP, con formularios reales de gasto/remesa, nuevo trabajo y persistencia. El caso también comprueba alta sencilla y Crear contextual; screenshots guardados en artifacts E2E. No se usa mobile-validation.html ni mocks de finanzas como evidencia. El workflow incluye el nuevo spec y conserva todos los anteriores; el recorrido avanzado cambia únicamente el botón de entrada a Configuración avanzada.

Verificación final del conjunto congelado:12PASS/26.47s en jerarquía/compatibilidad/recuperación;3 recorridos nativos PASS/1.1min con las12 combinaciones navegador/ancho y escritorio. El alta de Casa se realiza por UI sencilla, Techo por Añadir trabajo y los gastos/remesas por formularios reales; Crear móvil abre el mismo formulario contextual. Se conservan los límites de uso de la autorización de edición; las pruebas renuevan la credencial QA por el endpoint real cuando corresponde. Compatibilidad de huellas de idempotencia sin atribución y configuraciones previas verificada sin crear movimientos duplicados.

CI, SHA desplegado y resultado de migración productiva deben registrarse al ejecutarse en issue13. Este documento no anticipa un deploy ni una certificación financiera.
