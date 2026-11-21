import { describe, expect, it } from 'vitest'
import { distributeMonthlyCents } from './paymentScheduleUtils'

describe('cálculo de cuotas mensuales de AP', () => {
  it('cuadra el total y envía el residuo de centavos a la cuota final', () => {
    const plan = distributeMonthlyCents(10001n, 3, '2027-01', 31)
    expect(plan).toEqual([
      { dueDate: '2027-01-31', amountCents: 3333n },
      { dueDate: '2027-02-28', amountCents: 3333n },
      { dueDate: '2027-03-31', amountCents: 3335n },
    ])
    expect(plan.reduce((sum, item) => sum + item.amountCents, 0n)).toBe(10001n)
  })
  it('considera febrero bisiesto y cambio de año', () => {
    expect(distributeMonthlyCents(300n, 3, '2028-02', 31).map(item => item.dueDate))
      .toEqual(['2028-02-29', '2028-03-31', '2028-04-30'])
    expect(distributeMonthlyCents(200n, 2, '2026-12', 5).map(item => item.dueDate))
      .toEqual(['2026-12-05', '2027-01-05'])
  })
  it('rechaza montos que producirían cuotas de cero y fechas inválidas', () => {
    expect(() => distributeMonthlyCents(2n, 3, '2027-01', 1)).toThrow()
    expect(() => distributeMonthlyCents(500n, 2, '2027-13', 1)).toThrow()
    expect(() => distributeMonthlyCents(500n, 2, '2027-01', 0)).toThrow()
  })
})
