import { businessTodayIso } from './businessDate'

/** Diferencia de días CIVILES; UTC se usa solo para restar fechas sin huso local. */
export function daysUntilBusinessDate(dueDate: string, today = businessTodayIso()): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dueDate) || !/^\d{4}-\d{2}-\d{2}$/.test(today)) return null
  const parse = (s: string): number => {
    const [year, month, day] = s.split('-').map(Number)
    return Date.UTC(year, month - 1, day)
  }
  const due = parse(dueDate)
  const now = parse(today)
  if (!Number.isFinite(due) || !Number.isFinite(now)) return null
  return Math.round((due - now) / 86_400_000)
}
