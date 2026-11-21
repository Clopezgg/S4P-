import { describe, expect, it } from 'vitest'
import { filterNavGroups, navGroups, navItems } from './navigation'

describe('Navegación simplificada de S4P', () => {
  it('ofrece seis accesos diarios sin eliminar rutas existentes', () => {
    expect(navGroups.find(group => group.key === 'operacion')?.items).toHaveLength(6)
    const paths = navItems.map(item => item.path)
    expect(paths).toContain('/operacion/movimientos')
    expect(paths).toContain('/finanzas/conciliacion-subledger')
    expect(paths).toContain('/proyectos/wbs')
    expect(paths).toContain('/comercial/leads')
    expect(paths.length).toBe(new Set(paths).size)
  })
  it('respeta permisos y permite mostrar u ocultar funciones avanzadas', () => {
    const grants = ['project:read', 'treasury.account:read', 'contract.payment_schedule:read', 'core.company:read']
    const simple = filterNavGroups(grants)
    const advanced = filterNavGroups(grants, true)
    expect(simple.flatMap(group => group.items).some(item => item.path === '/proyectos/wbs')).toBe(false)
    expect(advanced.flatMap(group => group.items).some(item => item.path === '/proyectos/wbs')).toBe(false)
    expect(simple.flatMap(group => group.items).some(item => item.path === '/operacion/movimientos')).toBe(true)
    expect(advanced.flatMap(group => group.items).some(item => item.path === '/operacion/movimientos')).toBe(true)
  })
})
