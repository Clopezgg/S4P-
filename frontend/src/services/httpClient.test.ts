import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, apiFetchBlob, cancelPendingApiReads, clearEditCapability, friendlyApiMessage, storeEditCapability } from './httpClient'

describe('httpClient', () => {
  afterEach(() => {
    clearEditCapability()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'])('sends the unlocked capability for %s mutations', async (method) => {
    storeEditCapability('test-capability', Date.now() / 1000 + 60)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    await apiFetch('/approvals/example/decide', { method })
    expect(new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).get('X-Nexora-Edit-Access')).toBe('test-capability')
  })

  it('does not send an edit capability on reads', async () => {
    storeEditCapability('test-capability', Date.now() / 1000 + 60)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    await apiFetch('/approvals')
    expect(new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).has('X-Nexora-Edit-Access')).toBe(false)
  })

  it('dispatches nexora:session-expired on a 401 from a data endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { message: 'no session' } }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    const listener = vi.fn()
    window.addEventListener('nexora:session-expired', listener)

    await expect(apiFetch('/master-data/companies')).rejects.toBeInstanceOf(ApiError)
    expect(listener).toHaveBeenCalledTimes(1)

    window.removeEventListener('nexora:session-expired', listener)
  })

  it('does NOT dispatch nexora:session-expired for the auth probe itself', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 401, headers: { 'Content-Type': 'application/json' } })),
    )
    const listener = vi.fn()
    window.addEventListener('nexora:session-expired', listener)

    await expect(apiFetch('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(listener).not.toHaveBeenCalled()

    window.removeEventListener('nexora:session-expired', listener)
  })

  it('surfaces the backend correlation id and a friendly message on 5xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { message: 'boom', correlationId: 'abc-123' } }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    try {
      await apiFetch('/dashboard/summary')
      throw new Error('expected apiFetch to reject')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).correlationId).toBe('abc-123')
      expect(friendlyApiMessage(error)).toContain('abc-123')
    }
  })

  it('maps statuses to distinct human messages', () => {
    expect(friendlyApiMessage(new ApiError('x', 401))).toMatch(/sesión expiró/i)
    expect(friendlyApiMessage(new ApiError('x', 403))).toMatch(/permiso/i)
    expect(friendlyApiMessage(new ApiError('x', 404))).toMatch(/no existe/i)
    expect(friendlyApiMessage(new TypeError('network'))).toMatch(/conexión/i)
  })

  it('accepts a same-origin "/api" base URL in a production build (first-party auth)', async () => {
    vi.resetModules()
    vi.stubEnv('PROD', true)
    vi.stubEnv('VITE_API_BASE_URL', '/api')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )
    const mod = await import('./httpClient')
    await mod.apiFetch('/master-data/companies')
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/master-data/companies')
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('rejects a cleartext absolute base URL in a production build', async () => {
    vi.resetModules()
    vi.stubEnv('PROD', true)
    vi.stubEnv('VITE_API_BASE_URL', 'http://insecure.example/api')
    await expect(import('./httpClient')).rejects.toThrow(/HTTPS/i)
    vi.unstubAllEnvs()
    vi.resetModules()
  })
})


describe('pending API read cancellation', () => {
  afterEach(async () => {
    await cancelPendingApiReads()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function holdFetchUntilAbort() {
    const signals: AbortSignal[] = []
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, options?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = options?.signal
        if (!signal) throw new Error('A pending read must have an abort signal')
        signals.push(signal)
        signal.addEventListener('abort', () => reject(new DOMException('Read cancelled', 'AbortError')), { once: true })
      })))
    return signals
  }

  it('aborts and settles pending JSON reads before logout continues', async () => {
    const signals = holdFetchUntilAbort()
    const request = apiFetch('/treasury/accounts')
    const rejection = expect(request).rejects.toMatchObject({ name: 'AbortError' })
    await cancelPendingApiReads()
    await rejection
    expect(signals[0].aborted).toBe(true)
  })

  it('aborts pending private document downloads too', async () => {
    const signals = holdFetchUntilAbort()
    const request = apiFetchBlob('/treasury/vouchers/qa')
    const rejection = expect(request).rejects.toMatchObject({ name: 'AbortError' })
    await cancelPendingApiReads()
    await rejection
    expect(signals[0].aborted).toBe(true)
  })

  it('preserves cancellation from the query owner', async () => {
    const signals = holdFetchUntilAbort()
    const owner = new AbortController()
    const request = apiFetch('/treasury/accounts', { signal: owner.signal })
    const rejection = expect(request).rejects.toMatchObject({ name: 'AbortError' })
    owner.abort()
    await rejection
    expect(signals[0].aborted).toBe(true)
  })

  it('never cancels an in-flight financial POST', async () => {
    let finish: (response: Response) => void = () => undefined
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, _options?: RequestInit) =>
      new Promise<Response>(resolve => { finish = resolve })))
    const mutation = apiFetch('/ap/supplier-payments', { method: 'POST' })
    await cancelPendingApiReads()
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal).toBeUndefined()
    finish(new Response('{"id":"committed-payment"}', { status: 200 }))
    await expect(mutation).resolves.toEqual({ id: 'committed-payment' })
  })

  it('removes completed reads from the cancellation registry', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    await apiFetch('/treasury/accounts')
    const signal = vi.mocked(fetch).mock.calls[0]?.[1]?.signal
    await cancelPendingApiReads()
    expect(signal?.aborted).toBe(false)
  })
})
