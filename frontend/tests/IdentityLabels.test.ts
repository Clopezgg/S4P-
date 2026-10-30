import { describe, expect, it } from 'vitest'
import { displayUserName } from '../src/utils/identityLabels'

describe('S4P identity presentation', () => {
  it('displays the backend-provided public name without inventing a user', () => {
    expect(displayUserName('Administrador S4P', 'admin@example.test')).toBe('Administrador S4P')
    expect(displayUserName('Carlos López')).toBe('Carlos López')
  })
  it('falls back to email or a generic label', () => {
    expect(displayUserName('', 's4p@example.test')).toBe('s4p@example.test')
    expect(displayUserName(null, null)).toBe('Usuario')
  })
})
