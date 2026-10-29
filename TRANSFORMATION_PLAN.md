# S4P — Enterprise Platform: modernización y gobierno técnico

S4P es la identidad corporativa oficial de la plataforma. No debe existir una segunda marca de producto en el frontend, comprobantes públicos, nombres de aplicación, paquetes PWA o documentación de uso.

## Arquitectura mantenida
- React, TypeScript y Vite.
- FastAPI, PostgreSQL y Alembic.
- Despliegue actual: Render, con integración Supabase donde esté configurada.

## Reglas para la identidad
- Logotipo e isotipo oficiales: `brand/S4P/` y `frontend/public/`.
- Colores: azul institucional #101D35, oro mineral #C9A05A, marfil #F3F1EB y gris titanio #687485.
- Cualquier logo de empresa cliente permanece bajo administración de su propia entidad.
- No alterar cookies de sesión, claves de almacenamiento, encabezados API, esquemas ni endpoints persistidos sin migración versionada y pruebas.
- Probar login, navegación, comprobantes, PWA, E2E y finanzas tras cambios de marca.

No se certifica producción mediante cambios visuales solamente.
