import { expect, test } from '@playwright/test'

test('obra y trabajos: gastos y remesas reales sin mezclar Otros', async ({ page }) => {
  test.setTimeout(180_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill('admin@nexora.group')
  await page.getByLabel('Contraseña').fill(['Nexora', 'Admin', '123!'].join(''))
  await page.getByRole('button', { name: /iniciar sesión/i }).click()
  await expect(page).toHaveURL(/\/inicio/)
  await page.getByRole('button', { name: 'Edición protegida' }).click()
  const unlock = page.getByRole('dialog', { name: 'Desbloquear edición' })
  await unlock.getByLabel('Token de seguridad').fill(process.env.E2E_EDIT_ACCESS_TOKEN!)
  await unlock.getByRole('button', { name: 'Desbloquear', exact: true }).click()
  await expect(unlock).not.toBeVisible()
  const capability = await page.evaluate(() => sessionStorage.getItem('nexora.edit-access.capability'))
  expect(capability).toBeTruthy()
  const headers = { 'X-Nexora-Edit-Access': capability! }
  async function renew() {
    const result = await page.request.post('/api/edit-access/verify', { data: { token: process.env.E2E_EDIT_ACCESS_TOKEN } })
    expect(result.ok(), await result.text()).toBeTruthy()
    const body = await result.json() as { capability: string; expiresAt: number }
    headers['X-Nexora-Edit-Access'] = body.capability
    await page.evaluate(value => {
      sessionStorage.setItem('nexora.edit-access.capability', value.capability)
      sessionStorage.setItem('nexora.edit-access.expires-at', String(value.expiresAt))
    }, body)
  }
  async function post(path: string, data: Record<string, unknown>) {
    let response = await page.request.post(`/api${path}`, { headers, data })
    if (response.status() === 428) {
      await renew()
      response = await page.request.post(`/api${path}`, { headers, data })
    }
    expect(response.ok(), await response.text()).toBeTruthy()
    return await response.json() as { id: string }
  }
  const company = await post('/master-data/companies', { name: 'QA obra y trabajos', functionalCurrencyCode: 'HNL' })
  async function account(code: string, accountType: string) {
    return post('/master-data/accounts', { companyId: company.id, code, name: `${accountType} obra`, accountType })
  }
  const bankGl = await account('1100', 'ASSET')
  const capital = await account('3100', 'EQUITY')
  const expense = await account('5100', 'EXPENSE')
  const cash = await post('/treasury/accounts', { companyId: company.id, name: 'Caja de la empresa', kind: 'CASH', currencyCode: 'HNL', glAccountId: bankGl.id })
  await post('/treasury/remittances', { companyId: company.id, treasuryAccountId: cash.id, counterAccountId: capital.id,
    sender: 'Fondeo general QA', currencyCode: 'HNL', originalAmount: '10000.00', remittanceDate: '2026-11-13' })
  async function project(name: string, parentProjectId: string | null = null) {
    const created = await post('/projects', { companyId: company.id, name, parentProjectId, currencyCode: 'HNL' })
    await post(`/projects/${created.id}/status`, { status: 'ACTIVE' })
    return created
  }
  await page.evaluate(id => localStorage.setItem('nexora.activeCompanyId', id), company.id)
  await renew()
  await page.goto('/proyectos')
  await page.getByRole('button', { name: 'Nuevo proyecto', exact: true }).click()
  await page.getByLabel('Nombre del proyecto', { exact: true }).fill('Casa residencial')
  const [createdHouse] = await Promise.all([
    page.waitForResponse(response => new URL(response.url()).pathname === '/api/projects' && response.request().method() === 'POST' && response.status() === 201),
    page.getByRole('button', { name: 'Crear proyecto', exact: true }).click(),
  ])
  const house = await createdHouse.json() as { id: string }
  await expect(page.getByRole('heading', { level: 1, name: 'Casa residencial', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Registrar gasto', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Activar proyecto', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Activar proyecto', exact: true })).toHaveCount(0)
  const others = await project('Otros')
  const fence = await project('Verjas', house.id)
  const perimeter = await project('Cerco perimetral', house.id)
  for (const [target, amount] of [[house, '5.00'], [fence, '20.00'], [perimeter, '30.00'], [others, '444.00']] as const) {
    await post('/treasury/general-expenses', { companyId: company.id, treasuryAccountId: cash.id, expenseAccountId: expense.id,
      scope: 'PROJECT', projectId: target.id, category: 'materiales', amount, currencyCode: 'HNL', expenseDate: '2026-11-13', description: `Gasto QA ${amount}` })
  }
  await renew()
  const preferences = await page.request.put('/api/me/preferences', { headers, data: { themeId: 'sap-gui-horizon', density: 'compact' } })
  expect(preferences.ok(), await preferences.text()).toBeTruthy()
  const context = await page.request.put('/api/context', { headers, data: { activeProjectId: house.id } })
  expect(context.ok(), await context.text()).toBeTruthy()
  await page.evaluate(id => localStorage.setItem('nexora.activeCompanyId', id), company.id)
  await page.goto('/inicio')
  await expect(page.getByRole('heading', { level: 1, name: 'Casa residencial', exact: true })).toBeVisible()
  await page.getByLabel('Nuevo trabajo de esta obra').fill('Techo')
  await page.getByRole('button', { name: 'Añadir trabajo', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Techo', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Activar proyecto', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Activar proyecto', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Registrar gasto', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: 'Registrar salida / gasto' })
  await expect(dialog.getByText('Techo', { exact: true })).toBeVisible()
  await expect(dialog.getByLabel('Alcance del gasto')).toHaveCount(0)
  await dialog.getByLabel('Descripción').fill('Gasto del techo')
  await dialog.getByLabel('Monto (HNL)', { exact: true }).fill('40')
  await dialog.getByRole('button', { name: 'Registrar salida', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await page.getByRole('button', { name: 'Ver toda la obra: Casa residencial', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Casa residencial', exact: true })).toBeVisible()
  let expectedExpenses = 95
  for (const width of [360, 390, 430, 768]) {
    // Acquire the real finite-use capability again; never disable the guard.
    await renew()
    await page.setViewportSize({ width, height: 844 })
    await page.getByRole('button', { name: 'Registrar gasto', exact: true }).click()
    dialog = page.getByRole('dialog', { name: 'Registrar salida / gasto' })
    await expect(dialog.getByText('Casa residencial', { exact: true })).toBeVisible()
    await dialog.getByLabel('Descripción').fill(`Gasto casa ${width}`)
    await dialog.getByLabel('Monto (HNL)', { exact: true }).fill('1')
    await dialog.getByRole('button', { name: 'Registrar salida', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    expectedExpenses += 1
    await expect(page.locator('.nx-stat-card').filter({ hasText: 'Todos los gastos de esta obra' }).locator('.nx-stat-card__value')).toContainText(`${expectedExpenses}.00`)
    await page.getByRole('button', { name: 'Registrar remesa', exact: true }).click()
    const remittance = page.getByRole('dialog', { name: 'Registrar remesa' })
    await expect(remittance.getByText(/Remesa identificada para Casa residencial/)).toBeVisible()
    await remittance.getByLabel('Remitente', { exact: true }).fill('Aporte a Casa')
    await remittance.getByLabel('Monto (HNL)', { exact: true }).fill('10')
    await remittance.getByRole('button', { name: 'Registrar remesa', exact: true }).click()
    await expect(remittance).not.toBeVisible()
    const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }))
    expect(dimensions.scroll, `Obra @${width}`).toBeLessThanOrEqual(dimensions.client + 1)
    await expect(page.locator('#gastos-de-la-obra')).not.toContainText('444.00')
    await page.screenshot({ path: test.info().outputPath(`obra-${width}.png`), fullPage: true })
  }
  const total = await page.request.get(`/api/projects/${house.id}/spending`)
  expect(total.ok(), await total.text()).toBeTruthy()
  const data = await total.json() as { totalExpenses: string; totalRemittances: string; projects: { name: string }[] }
  expect(Number(data.totalExpenses)).toBe(99)
  expect(Number(data.totalRemittances)).toBe(40)
  expect(data.projects.map(p => p.name).sort()).toEqual(['Casa residencial', 'Cerco perimetral', 'Techo', 'Verjas'])
  await page.setViewportSize({ width: 390, height: 844 })
  const navigation = page.getByRole('navigation', { name: 'Navegación principal (móvil)' })
  await navigation.getByRole('button', { name: 'Crear', exact: true }).click()
  const sheet = page.getByRole('dialog', { name: 'Crear', exact: true })
  await sheet.getByRole('button', { name: 'Registrar gasto · Casa residencial', exact: true }).click()
  const contextualExpense = page.getByRole('dialog', { name: 'Registrar salida / gasto' })
  await expect(contextualExpense.getByText('Casa residencial', { exact: true })).toBeVisible()
  await contextualExpense.getByRole('button', { name: 'Cerrar', exact: true }).click()
  await expect(page).not.toHaveURL(/entry=expense/)
  await page.reload()
  await expect(page.locator('.nx-stat-card').filter({ hasText: 'Todos los gastos de esta obra' }).locator('.nx-stat-card__value')).toContainText('99.00')
  await expect(page.getByLabel('Proyecto seleccionado')).toHaveValue(house.id)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: test.info().outputPath('obra-desktop.png'), fullPage: true })
  expect(errors).toEqual([])
})
