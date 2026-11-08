# Seguridad

Controles inspeccionados: cookies HttpOnly/SameSite=Lax y Secure en producción; sesiones PostgreSQL; password Argon2id; Origin en mutaciones; headers de seguridad; capability de edición; RBAC backend con alcance empresa/proyecto y resolución de referencias anidadas. Los permisos UI mejoran navegación pero no sustituyen al backend. Las listas de permisos explícitos por función están en inventory.json; las dependencias globales también deben auditarse.

Se deben ejecutar auth, config_hardening, security_headers, edit_access, client_ip, rbac_and_company_isolation, project_scope_access y referencias de equipment/evidence. Las pruebas de dependencias y secretos son gates separados; ningún escaneo acredita ausencia total de vulnerabilidades. No se imprimen ni cambian secretos.

Hallazgo P0 reparado: el restore operacional podía borrar cualquier destino accesible por libpq. Ver DEFECTS.md y test_restore_script_safety. Las regresiones de rechazo usan ejecutables stub exclusivamente para demostrar ausencia de llamadas a PostgreSQL; la restauración y preservación se comprueban además con PostgreSQL real.

Pendientes: revisión exhaustiva IDOR de los 297 endpoints; carga maliciosa XSS en todos los campos/PDF, CSRF bajo Safari y topologías reales; análisis SQL dinámico; caché/logout con usuarios distintos; autorización de cada descarga y token QR. La suite existente cubre partes, no se atribuye cobertura no ejecutada. `_client_ip` confía en X-Forwarded-For del ingreso: verificar contrato específico de Render antes de certificar resistencia a spoofing.

La consulta a protección de main por GitHub REST devuelve 403 «Resource not accessible by integration». No demuestra protección ni ausencia de ella. No se debilitaron los controles para obtener acceso.

Auditorías locales del 8 de noviembre: pip-audit resolvió 85 dependencias runtime y no encontró vulnerabilidades conocidas. npm audit reportó 0 high/critical, 6 moderate y 2 low (8 total), con cadenas Vitest/mocker/UI y PWA/workbox/glob/deepmerge. Se conserva JSON completo. El workflow actual rechaza high/critical: un resultado CI verde no significa cero advisories. Intentar actualizar Vitest no produjo cambios versionados y la instalación adicional sufrió ENOSPC; no se afirma remediación de esas ocho alertas. Actualización compatible y regresiones siguen pendientes; no se usó downgrade de PWA ni overrides sin verificar para ocultarlas.
