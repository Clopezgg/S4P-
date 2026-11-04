import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'

test('mobile finance demo registers remittance and expense, downloads a valid example PDF', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/mobile-validation.html')
  await expect(page).toHaveTitle('S4P · Validación de interfaz móvil')
  const bottom = page.getByRole('navigation', { name: 'Navegación móvil' })
  await bottom.getByRole('button', { name: /Finanzas/i }).click()
  await page.getByRole('button', { name: 'Registrar remesa', exact: true }).first().click()
  const modal = page.getByRole('dialog', { name: /Registrar remesa/i })
  await expect(modal).toBeVisible()
  await modal.getByLabel('Remitente / quien envía').fill('Prueba de remesa')
  await modal.getByLabel('Empresa remesadora').fill('Entidad demo')
  await modal.getByLabel('Referencia de remesa').fill('REM-TEST-001')
  await modal.getByLabel('Monto').fill('1250.50')
  await modal.getByLabel('Concepto / descripción').fill('Prueba aislada de ingreso')
  await modal.getByRole('button', { name: 'Registrar en demostración' }).click()
  await expect(page.getByText('Remesa recibida · Prueba de remesa')).toBeVisible()

  await page.getByRole('button', { name: 'Registrar gasto', exact: true }).first().click()
  const expense = page.getByRole('dialog', { name: /Registrar gasto/i })
  await expense.getByLabel('Proveedor / beneficiario').fill('Proveedor de prueba')
  await expense.getByLabel('Categoría del gasto').selectOption('Servicios')
  await expense.getByLabel('Monto').fill('425')
  await expense.getByLabel('Concepto / descripción').fill('Gasto en demostracion')
  await expense.getByRole('button', { name: 'Registrar en demostración' }).click()
  await expect(page.getByText('Gasto registrado · Proveedor de prueba')).toBeVisible()

  await page.getByRole('button', { name: 'Generar recibo PDF', exact: true }).first().click()
  const receipt = page.getByRole('dialog', { name: /Generar recibo PDF/i })
  await receipt.getByLabel('Recibido de').fill('Persona ficticia')
  await receipt.getByLabel('Referencia del cobro').fill('COB-DEMO-01')
  await receipt.getByLabel('Monto').fill('680.75')
  await receipt.getByLabel('Concepto / descripción').fill('Validacion de recibo PDF')

  const downloadPromise = page.waitForEvent('download')
  await receipt.getByRole('button', { name: 'Generar PDF de ejemplo' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^S4P-RECIBO-DEMO-DEMO-\d{4}\.pdf$/)
  const buffer = await readFile(await download.path())
  expect(buffer.subarray(0, 8).toString('ascii')).toBe('%PDF-1.4')
  expect(buffer.toString('ascii')).toContain('SIN VALIDEZ CONTABLE')
  expect(buffer.toString('ascii')).toContain('%%EOF')
  await expect(page.getByText('Recibo de ingreso · Persona ficticia')).toBeVisible()
  const dimensions = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }))
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1)
})
