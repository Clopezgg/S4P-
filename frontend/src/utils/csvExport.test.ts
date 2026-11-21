import { describe, expect, it } from 'vitest'
import { serializeCsv } from './csvExport'

describe('exportación CSV financiera', () => {
  it('escapa comillas, conservando montos y caracteres internacionales', () => {
    const content = serializeCsv([['Concepto', 'Monto'], ['Café "El Sol"', '1250.25']])
    expect(content).toContain('"Café ""El Sol""","1250.25"')
    expect(content.startsWith('\uFEFF')).toBe(true)
  })
  it('neutraliza fórmulas introducidas en descripciones', () => {
    const content = serializeCsv([['=HYPERLINK("https://example.org")', '+cmd', '-malicioso', '@IMPORT', '-125.00']])
    expect(content).toContain("'=HYPERLINK")
    expect(content).toContain("'+cmd")
    expect(content).toContain("'-malicioso")
    expect(content).toContain("'@IMPORT")
    expect(content).toContain('"-125.00"')
  })
})
