/**
 * CSV compatible con Excel. Los textos no deben convertirse en fórmulas
 * al abrirse en hojas de cálculo.
 */
export function serializeCsv(rows: ReadonlyArray<ReadonlyArray<string | number | null | undefined>>): string {
  const cell = (value: string | number | null | undefined): string => {
    const raw = String(value ?? '')
    const trimmed = raw.trimStart()
    const looksNumeric = /^-?\d+(\.\d+)?$/.test(trimmed)
    const safe = /^[=+\-@]/.test(trimmed) && !looksNumeric ? "'" + raw : raw
    return '"' + safe.replace(/"/g, '""') + '"'
  }
  return '\uFEFF' + rows.map(row => row.map(cell).join(',')).join('\r\n')
}
