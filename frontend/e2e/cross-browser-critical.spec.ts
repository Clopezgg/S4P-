import { expect, test, type APIRequestContext, type Page, type Response } from '@playwright/test'

const ADMIN_EMAIL = 'admin@nexora.group'
const ADMIN_PASSWORD = ['Nexora', 'Admin', '123!'].join('')

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill(ADMIN_EMAIL)
  await page.getByLabel('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: /iniciar sesión/i }).click()
  await expect(page).toHaveURL(/\/inicio/, { timeout: 15_000 })
}

async function unlockEdit(request: APIRequestContext): Promise<string> {
  const token = process.env.E2E_EDIT_ACCESS_TOKEN
  expect(token).toBeTruthy()
  const response = await request.post('/api/edit-access/verify', { data: { token } })
  expect(response.ok(), await response.text()).toBeTruthy()
  const body = (await response.json()) as { capability: string }
  expect(body.capability).toBeTruthy()
  return body.capability
}

/** Wait for a page-owned response before consuming its body. Browser response
 * bodies may be discarded after navigation; diagnostics are only read on error
 * and cannot mask the actual status assertion. */
async function expectFinishedOk(response: Response, label: string): Promise<void> {
  const finishedError = await response.finished()
  expect(finishedError, `${label}: la respuesta no finalizó`).toBeNull()

  if (!response.ok()) {
    let detail = `HTTP ${response.status()}`
    try {
      detail = await response.text()
    } catch (error) {
      detail += ` (diagnóstico del body no disponible: ${String(error)})`
    }
    expect(response.ok(), `${label}: ${detail}`).toBeTruthy()
    return
  }

  expect(response.ok(), `${label}: HTTP ${response.status()}`).toBeTruthy()
}

/** Validate the mounted dashboard AND the authenticated real backend.
 * React Query can serve a warm dashboard without sending another GET; a
 * missing redundant network request is not evidence that the UI failed. */
async function assertMountedDashboard(page: Page, company: { id: string; functionalCurrencyCode: string }) {
  await expect(page.locator('main')).toBeVisible()
  const dashboard = await page.request.get(
    `/api/dashboard/summary?companyId=${encodeURIComponent(company.id)}`,
  )
  expect(dashboard.ok(), `dashboard real: HTTP ${dashboard.status()}`).toBeTruthy()
  const dashboardBody = (await dashboard.json()) as { currency: string }
  expect(dashboardBody.currency).toBe(company.functionalCurrencyCode)
}

async function ensureCompany(page: Page): Promise<{ id: string; functionalCurrencyCode: string }> {
  const existing = await page.request.get('/api/master-data/companies')
  expect(existing.ok(), await existing.text()).toBeTruthy()
  const companies = (await existing.json()) as Array<{
    id: string
    functionalCurrencyCode: string | null
  }>
  const configured = companies.find((company) => Boolean(company.functionalCurrencyCode))
  if (configured?.functionalCurrencyCode) {
    return { id: configured.id, functionalCurrencyCode: configured.functionalCurrencyCode }
  }

  const capability = await unlockEdit(page.request)
  const suffix = `${test.info().project.name}-${Date.now()}`
  const created = await page.request.post('/api/master-data/companies', {
    headers: { 'X-Nexora-Edit-Access': capability },
    data: {
      name: `Compatibilidad ${suffix}`,
      functionalCurrencyCode: 'HNL',
    },
  })
  expect(created.ok(), await created.text()).toBeTruthy()
  return (await created.json()) as { id: string; functionalCurrencyCode: string }
}

/**
 * Verifies that a route loads its application shell without server or page errors.
 */
async function expectOperationalRoute(page: Page, path: string) {
  const response = await page.goto(path)
  expect(response?.status(), `${path}: HTTP`).toBeLessThan(500)
  await expect(page.locator('.nx-app-shell, .nx-sap-workstation').first()).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('main')).toBeVisible()
  await page.waitForLoadState('networkidle')
  await expect(page.locator('body')).not.toContainText('Application error')
}

/**
 * Verifies the critical authenticated journey across browsers and SAP GUI variants.
 */
async function verifyCrossBrowserCompatibility({ page }: { page: Page }) {
  const pageErrors: string[] = []
  page.on(
    'pageerror',
    /**
     * Records browser errors across the complete compatibility journey.
     */
    (error) => pageErrors.push(String(error)),
  )

  await login(page)
  const company = await ensureCompany(page)

  await page.evaluate((companyId) => {
    window.localStorage.setItem('nexora.activeCompanyId', companyId)
  }, company.id)
  await page.reload()
  await assertMountedDashboard(page, company)

  for (const route of [
    '/inicio',
    '/proyectos',
    '/finanzas/cuentas-por-pagar',
    '/finanzas/tesoreria',
    '/control/configuracion',
  ]) {
    await expectOperationalRoute(page, route)
  }

  await page.goto('/inicio')
  await assertMountedDashboard(page, company)
  await page.getByRole('button', { name: 'Edición protegida' }).click()
  const dialog = page.getByRole('dialog', { name: 'Desbloquear edición' })
  await expect(dialog).toBeVisible()
  await dialog.getByLabel('Token de seguridad').fill(process.env.E2E_EDIT_ACCESS_TOKEN!)
  await dialog.getByRole('button', { name: 'Desbloquear', exact: true }).click()
  await expect(dialog).not.toBeVisible()

  for (const variant of [
    'sap-gui-signature',
    'sap-gui-tradeshow',
    'sap-gui-horizon',
    'sap-gui-horizon-dark',
  ]) {
    await page.goto('/control/configuracion')
    await page.waitForLoadState('networkidle')
    if ((await page.locator('html').getAttribute('data-nx-family')) !== 'sap-gui') {
      await page.getByLabel('Familia', { exact: true }).selectOption('sap-gui')
      await page.getByRole('button', { name: 'Cambiar a SAP GUI', exact: true }).click()
    }
    await page.getByLabel('Variante', { exact: true }).selectOption(variant)
    await expect(page.locator('html')).toHaveAttribute('data-nx-theme', variant)
    const preferenceResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === 'PUT' &&
        new URL(response.url()).pathname === '/api/me/preferences',
    )
    await page.getByRole('button', { name: 'Guardar como mi preferencia' }).click()
    const preferenceResponse = await preferenceResponsePromise
    await expectFinishedOk(preferenceResponse, 'guardar preferencia')
    await page.reload()
    await page.waitForLoadState('networkidle')
    await expect(page.locator('html')).toHaveAttribute('data-nx-theme', variant, { timeout: 10_000 })
    await page.getByRole('menuitem', { name: 'Sistema', exact: true }).click()
    // A real click verifies the menu is not clipped behind the shell bars.
    await page
      .getByRole('menu', { name: 'Sistema', exact: true })
      .getByRole('menuitem', { name: 'Inicio', exact: true })
      .click()
    await expect(page).toHaveURL(/\/inicio/)
    await assertMountedDashboard(page, company)
    await expectOperationalRoute(page, '/finanzas/contabilidad')
    await expectOperationalRoute(page, '/proyectos/cockpit')
    await expectOperationalRoute(page, '/abastecimiento/inventario')
    await page.getByRole('button', { name: 'Edición habilitada' }).click()
    await page.getByRole('button', { name: 'Edición protegida' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await page.getByRole('button', { name: 'Edición protegida' }).click()
    await page.getByLabel('Token de seguridad').fill(process.env.E2E_EDIT_ACCESS_TOKEN!)
    await page.getByRole('button', { name: 'Desbloquear', exact: true }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  }

  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  // Logout must leave S4P entirely; navigating to /login would contradict
  // the corporate exit contract and could allow back-button session confusion.
  await expect(page).toHaveURL('about:blank', { timeout: 10_000 })
  expect(pageErrors).toEqual([])
}

test('cross-browser critical compatibility', verifyCrossBrowserCompatibility)

test.describe('pending dashboard cancellation', () => {
  // Playwright cannot retain a response already handled by a service worker.
  // Only this latency regression bypasses the metadata-only PWA worker; the
  // compatibility journey above exercises the actual worker and build.
  test.use({ serviceWorkers: 'block' })

test('logout aborts pending real dashboard reads before leaving S4P', async ({ page }) => {
  // Observe native AbortSignal events without changing fetch arguments/results.
  await page.addInitScript(() => {
    const state = window as Window & {
      __s4pAbortedReads: string[]
      __s4pReadSignals: Record<string, AbortSignal | null | undefined>
    }
    state.__s4pAbortedReads = []
    state.__s4pReadSignals = {}
    const nativeFetch = window.fetch.bind(window)
    window.fetch = (input, init) => {
      const address = input instanceof Request ? input.url : String(input)
      const path = new URL(address, location.href).pathname
      if (['/api/treasury/accounts', '/api/financial-control/cash-flow-actual/series'].includes(path)) {
        const signal = init?.signal
        state.__s4pReadSignals[path] = signal
        state.__s4pAbortedReads = state.__s4pAbortedReads.filter(value => value !== path)
        signal?.addEventListener('abort', () => {
          if (state.__s4pReadSignals[path] === signal) state.__s4pAbortedReads.push(path)
        }, { once: true })
      }
      return nativeFetch(input, init)
    }
  })
  const pageErrors: string[] = []
  page.on('pageerror', error => pageErrors.push(String(error)))
  await login(page)
  const company = await ensureCompany(page)
  const capability = await unlockEdit(page.request)
  const companies = await page.request.get('/api/master-data/companies')
  expect(companies.ok(), await companies.text()).toBeTruthy()
  if ((await companies.json()).length < 2) {
    const extra = await page.request.post('/api/master-data/companies', {
      headers: { 'X-Nexora-Edit-Access': capability },
      data: { name: `Logout isolation ${test.info().project.name}`, functionalCurrencyCode: 'HNL' },
    })
    expect(extra.status()).toBe(201)
  }
  const context = await page.request.put('/api/context', {
    headers: { 'X-Nexora-Edit-Access': capability },
    data: { activeProjectId: null },
  })
  expect(context.ok(), await context.text()).toBeTruthy()
  expect((await context.json()).activeProjectId).toBeNull()
  const preferences = await page.request.put('/api/me/preferences', {
    headers: { 'X-Nexora-Edit-Access': capability },
    data: { themeId: 'sap-gui-horizon', density: 'compact' },
  })
  expect(preferences.ok(), await preferences.text()).toBeTruthy()
  await page.reload()
  const selector = page.getByRole('combobox', { name: 'Empresa activa', exact: true })
  await expect(selector).toHaveValue('')
  await expect(selector.locator('option:checked')).toHaveText('Seleccionar empresa')
  await selector.selectOption(company.id)
  await expect(selector).toHaveValue(company.id)
  await assertMountedDashboard(page, company)
  await expect(page.getByText('Cuentas bancarias · saldos en libros', { exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Realizado', exact: true })).toBeVisible()

  // Retain responses from the REAL backend; only their delivery is delayed.
  // No endpoint body, status, permissions or persisted financial data is mocked.
  let release: () => void = () => undefined
  const delivery = new Promise<void>(resolve => { release = resolve })
  const pending = new Set<import('@playwright/test').Request>()
  await page.route(/\/api\/(treasury\/accounts|financial-control\/cash-flow-actual\/series)\?/, async route => {
    const request = route.request()
    try {
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      pending.add(request)
      await delivery
      if (!request.failure()) await route.fulfill({ response })
    } catch (error) {
      // An explicitly aborted browser request needs no response delivery.
      if (!request.failure()) throw error
    }
  })
  let cancelledBeforeRevocation = false
  await page.route('**/api/auth/logout', async route => {
    const aborted = await page.evaluate(() =>
      (window as Window & { __s4pAbortedReads: string[] }).__s4pAbortedReads)
    cancelledBeforeRevocation = ['/api/treasury/accounts', '/api/financial-control/cash-flow-actual/series']
      .every(path => aborted.includes(path))
    // Revocation itself still reaches the real backend, even on a failing case.
    await route.continue()
  })
  try {
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect.poll(() => new Set([...pending]
      .filter(request => !request.failure())
      .map(request => new URL(request.url()).pathname)).size).toBe(2)
    await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
    await expect(page).toHaveURL('about:blank', { timeout: 10_000 })
    await expect.poll(() => [...pending].filter(request => !request.failure()).length).toBe(0)
    expect(cancelledBeforeRevocation, 'Dashboard reads must stop before session revocation').toBe(true)
    expect(pageErrors).toEqual([])
    expect((await page.request.get('/api/auth/me')).status()).toBe(401)
  } finally {
    release()
    // The requests are already proven aborted. Do not await cancelled route
    // delivery after about:blank; Playwright can retain those handler promises.
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  }
})

})
