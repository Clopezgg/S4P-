/** Distribuye importes monetarios en centavos sin errores de coma flotante.
 * Este calendario es un FORECAST de AP, no una orden ni autorización de pago.
 */
export function distributeMonthlyCents(
  totalCents: bigint, months: number, firstMonth: string, dueDay: number,
): { dueDate: string; amountCents: bigint }[] {
  const match = /^(\d{4})-(\d{2})$/.exec(firstMonth)
  if (!match || !Number.isInteger(months) || months < 1 || months > 36
    || !Number.isInteger(dueDay) || dueDay < 1 || dueDay > 31
    || Number(match[2]) < 1 || Number(match[2]) > 12
    || Number(match[1]) < 1 || totalCents < BigInt(months)) {
    throw new Error('Parámetros inválidos: cada cuota debe tener al menos un centavo')
  }

  const startingIndex = Number(match[1]) * 12 + Number(match[2]) - 1
  const base = totalCents / BigInt(months)
  const residue = totalCents % BigInt(months)

  return Array.from({ length: months }, (_, i) => {
    const index = startingIndex + i
    const year = Math.floor(index / 12)
    const month = (index % 12) + 1
    const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate()
    const day = Math.min(dueDay, lastDay)
    return {
      dueDate: [year.toString().padStart(4, '0'), String(month).padStart(2, '0'), String(day).padStart(2, '0')].join('-'),
      amountCents: base + (i === months - 1 ? residue : 0n),
    }
  })
}
