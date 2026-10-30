import { describe, expect, it } from 'vitest'
import { displayUserName } from '../src/utils/identityLabels'

describe('S4P user identity labels', () => {
  it('shows S4P for the exact imported generic administrator name', () => {
    expect(displayUserName('Administrador Nexora', 'admin@example.test')).toBe('Administrador S4P')
    expect(displayUserName('administrador NEXORA GROUP')).toBe('Administrador S4P')
  })

  it('never rewrites personal or legally meaningful names', () => {
    expect(displayUserName('Carlos Nexora', 'x@example.test')).toBe('Carlos Nexora')
    expect(displayUserName('Administrador Nexora Regional')).toBe('Administrador Nexora Regional')
    expect(displayUserName('Carlos López')).toBe('Carlos López')
    expect(displayUserName('', 's4p@example.test')).toBe('s4p@example.test')
  })
})
