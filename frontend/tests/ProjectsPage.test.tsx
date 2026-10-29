import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderApp } from './testUtils'

function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/auth/me')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ id: 'u1', email: 'admin@nexora.group', fullName: 'Admin', roles: ['Administrator'] }),
        } as Response)
      }
      for (const [fragment, body] of Object.entries(routes)) {
        if (url.includes(fragment)) {
          return Promise.resolve({ ok: true, status: 200, json: async () => body } as Response)
        }
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) } as Response)
    }),
  )
}

describe('ProjectsPage', () => {
  it('lets a new administrator create a company before starting project setup', async () => {
    stubFetch({ '/master-data/companies': [] })

    render(renderApp('/proyectos'))

    expect(await screen.findByText(/configuración inicial · crear compañía/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/nombre de la compañía/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /crear compañía y habilitar operaciones/i })).toBeDisabled()
    expect(screen.queryByText('Sin proyectos')).not.toBeInTheDocument()
  })

  it('creates the first company from Projects and enables the guided project wizard', async () => {
    const company = { id: 'first-company', name: 'S4P Construcción', code: 'S4P', functionalCurrencyCode: 'HNL' }
    let created = false
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/auth/me')) return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ id: 'u1', email: 'admin@s4p.test', fullName: 'Admin', roles: ['Administrator'] }),
      } as Response)
      if (url.includes('/master-data/companies')) {
        if (init?.method === 'POST') {
          created = true
          return Promise.resolve({ ok: true, status: 201, json: async () => company } as Response)
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => created ? [company] : [] } as Response)
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => [] } as Response)
    }))

    render(renderApp('/proyectos'))
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(/nombre de la compañía/i), company.name)
    await user.click(screen.getByRole('button', { name: /crear compañía y habilitar operaciones/i }))
    expect(await screen.findByRole('button', { name: 'Nuevo proyecto' })).toBeInTheDocument()
  })

  it('lists real projects for the selected company', async () => {
    stubFetch({
      '/master-data/companies': [{ id: 'c1', name: 'Constructora Nexora', code: null, legalName: null, functionalCurrencyCode: 'HNL', country: null, fiscalId: null }],
      '/projects?company_id=c1': [
        { id: 'p1', companyId: 'c1', name: 'Torre Nexora II', code: 'PRJ-001', customerRef: null, manager: null, currencyCode: 'HNL', costCenterId: null, plannedStart: null, plannedEnd: null, actualEnd: null, status: 'PLANNING', description: null },
      ],
    })

    render(renderApp('/proyectos'))

    expect(await screen.findByText('Torre Nexora II')).toBeInTheDocument()
    const row = screen.getByText('Torre Nexora II').closest('tr') as HTMLElement
    expect(within(row).getByText('Planificación')).toBeInTheDocument()
  })

  it('creates a project through the guided wizard, sending the real location (§11/§17)', async () => {
    let createPayload: Record<string, unknown> | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = init?.method ?? 'GET'
        if (url.includes('/auth/me')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ id: 'u1', email: 'a@nexora.group', fullName: 'Admin', roles: ['Administrator'] }) } as Response)
        }
        if (url.includes('/master-data/companies')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [{ id: 'c1', name: 'Constructora Nexora', code: null, legalName: null, functionalCurrencyCode: 'HNL' }] } as Response)
        }
        if (url.includes('/master-data/users')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [{ id: 'mgr1', fullName: 'Ing. Responsable' }] } as Response)
        }
        if (url.endsWith('/projects/setup-runs') && method === 'POST') {
          createPayload = JSON.parse(String(init?.body))
          return Promise.resolve({ ok: true, status: 201, json: async () => ({ id: 'setup9', companyId: 'c1', status: 'DRAFT', activate: false, projectId: null, failureStep: null, failureMessage: null, stagedDocumentCount: 0 }) } as Response)
        }
        if (url.endsWith('/projects/setup-runs/setup9/execute') && method === 'POST') {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ id: 'setup9', companyId: 'c1', status: 'COMPLETED', activate: false, projectId: 'p9', failureStep: null, failureMessage: null, stagedDocumentCount: 0 }) } as Response)
        }
        if (url.endsWith('/projects/p9')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ id: 'p9', companyId: 'c1', name: 'Puente Río Grande', status: 'PLANNING' }) } as Response)
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] } as Response)
      }),
    )

    render(renderApp('/proyectos'))
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo proyecto' }))
    await userEvent.type(screen.getByLabelText('Nombre del proyecto'), 'Puente Río Grande')
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    // Paso 2 — ubicación real.
    await userEvent.type(screen.getByLabelText('Ciudad'), 'Comayagua')
    await userEvent.type(screen.getByLabelText('Departamento / Estado'), 'Comayagua')
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' })) // alcance
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' })) // equipo
    await userEvent.click(screen.getByRole('button', { name: 'Crear como borrador' }))

    await waitFor(() =>
      expect(createPayload).toMatchObject({
        project: expect.objectContaining({
          name: 'Puente Río Grande',
          city: 'Comayagua',
          stateDepartment: 'Comayagua',
        }),
      }),
    )
  })

  it('does not allow a draft with only one of the required WBS fields', async () => {
    stubFetch({
      '/master-data/companies': [{ id: 'c1', name: 'Constructora Nexora', code: null, legalName: null, functionalCurrencyCode: 'HNL' }],
      '/projects?company_id=c1': [],
    })

    render(renderApp('/proyectos'))
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo proyecto' }))
    await userEvent.type(screen.getByLabelText('Nombre del proyecto'), 'WBS incompleta')
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))

    await userEvent.type(screen.getByLabelText('Código WBS'), '1.0')

    expect(screen.getByText('Completa código y nombre WBS o deja ambos vacíos.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crear como borrador' })).toBeDisabled()
  })
})
