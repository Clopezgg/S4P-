import { describe, expect, it } from 'vitest'
import { daysUntilBusinessDate } from './dueDateUtils'

describe('calendario de vencimientos', () => {
  it('cuenta días civiles cruzando meses y años', () => {
    expect(daysUntilBusinessDate('2027-01-01', '2026-12-30')).toBe(2)
    expect(daysUntilBusinessDate('2027-01-01', '2027-01-01')).toBe(0)
    expect(daysUntilBusinessDate('2026-11-20', '2026-11-21')).toBe(-1)
  })
  it('conserva el día bisiesto al calcular el vencimiento', () => {
    expect(daysUntilBusinessDate('2028-03-01', '2028-02-28')).toBe(2)
  })
  it('rechaza fechas inválidas y formatos que no son civiles', () => {
    expect(daysUntilBusinessDate('mañana', '2026-11-21')).toBeNull()
    expect(daysUntilBusinessDate('2026-02-30', '2026-02-27')).toBeNull()
    expect(daysUntilBusinessDate('2027-02-29', '2027-02-28')).toBeNull()
    expect(daysUntilBusinessDate('2028-02-29', '2028-02-28')).toBe(1)
  })
})
