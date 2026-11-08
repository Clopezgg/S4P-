# Registro de ejecución local

2026-11-08 UTC, baseline a2ff300..., PostgreSQL local 16.15; producción nunca usada como destino de QA.

| Acción | Resultado / límite |
|---|---|
| npm ci | completó en frontend del baseline |
| npm run typecheck, lint, test, build | PASS: 79 archivos, 273 tests; Vite 1002 módulos, build 10.53s |
| Ruff backend y script inventario | PASS |
| compileall backend/app, bash -n db_restore.sh | PASS |
| test_restore_script_safety + test_backup_restore + dos AP afectados por DiskFull | 9 passed en 14.58s, PostgreSQL real para restore/AP |
| Primer pytest completo | interrumpido para diagnosticar DiskFull: 46 passed, 1 failed + 1 error ambientales; no suite completa verde |
| Segundo pytest completo | interrumpido por DiskFull: 112 passed, 3 failed ambientales de backup/tempfile; no suite completa verde |
| Tercer pytest -x | 65 tests pasaron; setup siguiente falló DiskFull. No cuenta como 767/767 |
| Playwright WebKit, configuración local de librerías | PASS: dos escenarios móviles y compatibilidad desktop en ejecución de seis escenarios; los tres Chromium de esa ejecución fallaron con entorno contaminado |
| Chromium repetición | PASS compatibilidad desktop y shell moderno móvil; SAP móvil contaminado por ENOSPC, requiere repetición limpia |
| pip-audit runtime | PASS 85 dependencias, cero advisories conocidos |
| npm audit | 6 moderate + 2 low; 0 high/critical. No remediados |
| main protection REST | BLOCKED HTTP 403 |
| Render read-only SQL | BLOCKED allowlist externa vacía, mantenida |
| Restore cifrado productivo | BLOCKED sin clave/bridge en entorno; fixture local no lo sustituye |

Los tests de backend se recolectan: 767. El listado de tests del inventario es por archivo, no por caso parametrizado. La ejecución completa debe acreditarse mediante una nueva corrida local con capacidad suficiente o jobs CI **push** del commit final y logs; las corridas parciales no se declaran éxito global. El CI de baseline no acredita las modificaciones nuevas.

Repetición final dirigida: `test_restore_script_safety.py`, `test_backup_restore.py`, `test_render_startup_gate.py`: **9 passed, 8.52s**. Incluye verificación del startup Alembic read-only. Chromium SAP móvil volvió a fallar con `net::ERR_INSUFFICIENT_RESOURCES` al cargar módulos Vite y ENOSPC al guardar captura; la traza ZIP se inspeccionó y contiene esos errores. No se elimina la aserción de main visible ni se considera verificado ese escenario en Chromium local. WebKit y Chromium moderno/desktop sí tienen escenarios exitosos, sin equivaler a aceptación móvil total.
