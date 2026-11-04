import { expect, test, type Page } from '@playwright/test'

// Mobile uses the real isolated E2E backend and shared RBAC (no mocked API).
async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill('admin@nexora.group')
  await page.getByLabel('Contraseña').fill(['Nexora', 'Admin', '123!'].join(''))
  await page.getByRole('button', { name: /iniciar sesión/i }).click()
  await expect(page).toHaveURL(/\/inicio/, { timeout: 15_000 })
}

async function selectTheme(page: Page, themeId: string) {
  const response = await page.request.post('/api/edit-access/verify', {
    data: { token: process.env.E2E_EDIT_ACCESS_TOKEN },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  const { capability } = (await response.json()) as { capability: string }
  const result = await page.request.put('/api/me/preferences', {
    headers: { 'X-Nexora-Edit-Access': capability },
    data: { themeId, density: 'compact' },
  })
  expect(result.ok(), await result.text()).toBeTruthy()
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-nx-theme', themeId)
}

async function noDocumentOverflow(page: Page, label: string) {
  const width = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }))
  expect(width.scroll, label + ': no horizontal page scroll').toBeLessThanOrEqual(width.client + 1)
}

test('mobile S4P SAP navigation, company selector and create sheet remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await signIn(page)
  await selectTheme(page, 'sap-gui-horizon')
  const navigation = page.getByRole('navigation', { name: 'Navegación principal (móvil)' })
  await expect(navigation).toBeVisible()
  await expect(navigation.getByRole('link', { name: 'Inicio' })).toBeVisible()
  await expect(page.locator('.nx-sap-menubar')).toBeHidden()
  await expect(page.locator('.nx-sap-titlebar')).toBeHidden()
  await expect(page.locator('.nx-topbar__mobile-brand')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Proyecto seleccionado' })).toBeVisible()
  await noDocumentOverflow(page, 'SAP mobile home')
  await navigation.getByRole('button', { name: 'Más' }).click()
  const drawer = page.getByRole('dialog', { name: 'Navegación' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByLabel('Empresa activa')).toBeVisible()
  await expect(drawer.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
  await drawer.getByRole('button', { name: 'Cerrar', exact: true }).click()
  await expect(drawer).toBeHidden()
  await navigation.getByRole('button', { name: 'Crear' }).click()
  const sheet = page.getByRole('dialog', { name: 'Crear' })
  await expect(sheet).toBeVisible()
  await sheet.getByRole('button', { name: 'Cerrar', exact: true }).click()
  await expect(sheet).toBeHidden()
  for (const viewport of [360, 390, 430, 768]) {
    await page.setViewportSize({ width: viewport, height: 844 })
    for (const route of ['/inicio', '/proyectos', '/finanzas/tesoreria', '/control/configuracion']) {
      const result = await page.goto(route)
      expect(result?.status(), route + ': HTTP status').toBeLessThan(500)
      await expect(page.locator('main')).toBeVisible()
      await noDocumentOverflow(page, route + ' @' + viewport)
      await expect(navigation).toBeVisible()
    }
  }
})

test('modern mobile workspace offers navigation and safe company switching', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 })
  await signIn(page)
  await selectTheme(page, 's4p-horizon-light')
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.webmanifest')
  const manifestResponse = await page.request.get('/manifest.webmanifest')
  expect(manifestResponse.ok()).toBeTruthy()
  expect((await manifestResponse.json()).display).toBe('standalone')
  const nav = page.getByRole('navigation', { name: 'Navegación principal (móvil)' })
  await expect(nav).toBeVisible()
  await nav.getByRole('button', { name: 'Más' }).click()
  const drawer = page.getByRole('dialog', { name: 'Navegación' })
  await expect(drawer.getByLabel('Empresa activa')).toBeVisible()
  await drawer.getByRole('button', { name: 'Cerrar', exact: true }).click()
  await nav.getByRole('button', { name: 'Crear' }).click()
  await expect(page.getByRole('dialog', { name: 'Crear' })).toBeVisible()
  await page.getByRole('dialog', { name: 'Crear' }).getByRole('button', { name: 'Cerrar', exact: true }).click()
  for (const width of [360, 390, 430, 768]) {
    await page.setViewportSize({ width, height: 844 })
    await noDocumentOverflow(page, 'Modern mobile @' + width)
    await expect(nav).toBeVisible()
  }
})
