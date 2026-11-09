# S4P — auditoría ejecutada, 8–9 de noviembre de 2026

Estado: **NO-GO financiero**. Este expediente no es una certificación ni acredita todas las acciones del ERP. El baseline inspeccionado es `a2ff300696f7be81ef1afd2116f19d83010af56f` de `main`; referencia Nexora `2ca980446654f3c92e3ddb1e8f55d847ef073968`. Solo se trabaja en main, issue #13; no se repite PR #11.

Última continuación: [CONTINUITY_2026-11-09.md](CONTINUITY_2026-11-09.md). Conserva el baseline histórico y distingue las verificaciones posteriores.

## Evidencia y alcance

- `inventory.json`: funciones Python con firma, docstring, llamadas, permisos explícitos y excepciones; endpoints; modelos completos; imports, rutas y controles detectados del frontend; migraciones, tests, dependencias y workflows. Es descubrimiento estático, **no ejecución exhaustiva de cada control**.
- `FUNCTION_MATRIX.md`: 297 endpoints clasificados PARCIAL hasta asociar ejecución y persistencia por acción. Dependencias y guards globales requieren revisión: ausencia de `require_permission` en la función no implica endpoint público.
- `openapi.json`: esquema generado desde la aplicación real sin conectarse a producción; 235 paths efectivos, incluidos métodos compartidos.
- `schema-metadata.json`: 111 tablas, columnas, tipos, nulabilidad, FK, índices y constraints declarados por SQLAlchemy. Las constraints instaladas mediante migración requieren comprobación separada en PostgreSQL.
- `evidence/baseline-ci.json`: seis ejecuciones **push** del baseline, con jobs y pasos. No acredita futuros commits.
- `ARCHITECTURE.md`, `FINANCE.md`, `SECURITY.md`, `DB_BACKUP.md`, `MOBILE_PDF.md`, `RELEASE.md`: trazabilidad, limitaciones y gates.
- `DEFECTS.md`: causa raíz, reparación y riesgos pendientes.

Reproducir el inventario: `python scripts/audit_inventory.py`, con Nexora en el directorio hermano `nexora-group`. Los JSON de OpenAPI y metadatos se generan importando `app.main` y `Base` con configuración local, sin ejecutar lifespan. El inventario no resuelve dinámicamente todos los handlers JSX ni demuestra ausencia de código muerto.

La clasificación VERIFICADA se reserva al comportamiento y entorno nombrados en la evidencia de ejecución; PARCIAL = código/alguna capa comprobada; ROTA = fallo reproducido de la función; SIMULADA = datos deliberadamente ficticios; NO IMPLEMENTADA = ausencia demostrada; BLOQUEADA = impedimento documentado. No convertir un test con stub de transporte en prueba productiva.
