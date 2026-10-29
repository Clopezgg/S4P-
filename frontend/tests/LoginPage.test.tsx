import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp } from './testUtils'

describe('LoginPage', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: async () => ({ detail: 'Not authenticated' }),
      } as Response),
    )
  })

  it('renders the minimalist login card when the user is not authenticated', async () => {
    render(renderApp('/login'))

    expect(await screen.findByRole('heading', { name: /bienvenido a s4p/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/correo electrónico/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /iniciar sesión/i })).toBeInTheDocument()
  })

  it('does not surface a non-functional "forgot password" affordance', async () => {
    render(renderApp('/login'))
    await screen.findByRole('heading', { name: /bienvenido a s4p/i })
    expect(screen.queryByText(/olvidaste tu contraseña/i)).not.toBeInTheDocument()
  })

  it('toggles password visibility', async () => {
    const user = userEvent.setup()
    render(renderApp('/login'))
    await screen.findByRole('heading', { name: /bienvenido a s4p/i })

    const password = screen.getByLabelText(/contraseña/i)
    expect(password).toHaveAttribute('type', 'password')
    await user.click(screen.getByRole('button', { name: /mostrar/i }))
    expect(password).toHaveAttribute('type', 'text')
  })

  it('shows validation errors for empty submit', async () => {
    const user = userEvent.setup()
    render(renderApp('/login'))

    await screen.findByRole('heading', { name: /bienvenido a s4p/i })
    await user.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    expect(await screen.findByText(/ingresa tu correo electrónico/i)).toBeInTheDocument()
  })

  it('shows a safe, human message on failed credentials (never a status code)', async () => {
    // Readiness is a separate GET and must return real JSON before the
    // login request; an SPA fallback HTML must never receive a password.
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes('/api/readyz')) {
        return {
          ok: true, status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ status: 'ok' }),
        } as Response
      }
      return {
        ok: false, status: 401, headers: new Headers(),
        json: async () => ({ detail: 'Invalid credentials' }),
      } as Response
    }))
    const user = userEvent.setup()
    render(renderApp('/login'))
    await screen.findByRole('heading', { name: /bienvenido a s4p/i })

    await user.type(screen.getByLabelText(/correo electrónico/i), 'admin@s4p.group')
    await user.type(screen.getByLabelText(/contraseña/i), 'wrong-pass')
    await user.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    expect(await screen.findByText(/correo o contraseña incorrectos/i)).toBeInTheDocument()
  })
  it('never submits credentials to an HTML-only preview and offers the connected ERP', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true, status: 200,
      headers: new Headers({ 'content-type': 'text/html' }),
      text: async () => '<!doctype html>',
    } as Response))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(renderApp('/login'))
    await screen.findByRole('heading', { name: /bienvenido a s4p/i })
    await user.type(screen.getByLabelText(/correo electrónico/i), 'admin@example.test')
    await user.type(screen.getByLabelText(/contraseña/i), 'never-send-this-password')
    await user.click(screen.getByRole('button', { name: /iniciar sesión/i }))
    expect(await screen.findByRole('link', { name: /abrir s4p con acceso al servidor/i })).toHaveAttribute(
      'href', 'https://s4p-erp-api.onrender.com/login',
    )
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls.some((args) => String(args[0]).endsWith('/api/auth/login'))).toBe(false)
  })

})
