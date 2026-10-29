import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../src/features/auth/AuthProvider'
import { useAuth } from '../src/features/auth/auth-context'
import { exitApplication } from '../src/features/auth/exitApplication'

vi.mock('../src/features/auth/exitApplication', () => ({
  exitApplication: vi.fn(),
}))

function LogoutButton() {
  const { logout, isAuthenticated } = useAuth()
  return (
    <div>
      <span>{isAuthenticated ? 'Sesión activa' : 'Sesión inactiva'}</span>
      <button onClick={logout}>Salir</button>
    </div>
  )
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><AuthProvider><LogoutButton /></AuthProvider></QueryClientProvider>)
  return client
}

const currentUser = {
  id: 'u1', email: 'admin@example.test', fullName: 'Administrador S4P',
  roles: ['Administrator'], permissions: [],
}

describe('S4P complete sign-out', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('alert', vi.fn())
    window.localStorage.setItem('nexora.activeCompanyId', 'test-company')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/auth/me')) {
        return { ok: true, status: 200, json: async () => currentUser } as Response
      }
      if (String(input).endsWith('/auth/logout')) {
        return { ok: true, status: 204 } as Response
      }
      throw new Error('Unexpected endpoint')
    }))
  })

  it('revokes the session on the server, discards cached company and exits the ERP', async () => {
    const user = userEvent.setup()
    const client = setup()
    await screen.findByText('Sesión activa')
    await user.click(screen.getByRole('button', { name: 'Salir' }))
    await waitFor(() => expect(exitApplication).toHaveBeenCalledOnce())
    expect(fetch).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({
      method: 'POST', credentials: 'include',
    }))
    expect(window.localStorage.getItem('nexora.activeCompanyId')).toBeNull()
    expect(client.getQueryData(['auth', 'me'])).toBeUndefined()
    expect(window.alert).not.toHaveBeenCalled()
  })

  it('does not leave or report success when server revocation fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/auth/me')) {
        return { ok: true, status: 200, json: async () => currentUser } as Response
      }
      return {
        ok: false, status: 503, headers: new Headers(),
        json: async () => ({ detail: 'Service unavailable' }),
      } as Response
    }))
    const user = userEvent.setup()
    setup()
    await screen.findByText('Sesión activa')
    await user.click(screen.getByRole('button', { name: 'Salir' }))
    await waitFor(() => expect(window.alert).toHaveBeenCalledOnce())
    expect(exitApplication).not.toHaveBeenCalled()
    expect(screen.getByText('Sesión activa')).toBeInTheDocument()
  })
})
