import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../src/features/auth/auth-context'
import { useActiveCompany } from '../src/hooks/useActiveCompany'
import { masterDataService } from '../src/services/masterDataService'

const testUser: AuthContextValue['user'] = {
  id: 'u-auth-test',
  email: 'test@example.test',
  fullName: 'QA S4P',
  roles: ['Administrator'],
  permissions: [],
}

function CompanyProbe() {
  const { companies } = useActiveCompany()
  return <output data-testid="companies">{companies.length}</output>
}

function Fixture() {
  const [authenticated, setAuthenticated] = useState(false)
  const auth: AuthContextValue = {
    user: authenticated ? testUser : null,
    isLoading: !authenticated,
    isAuthenticated: authenticated,
    login: async () => testUser!,
    loginError: null,
    isLoggingIn: false,
    logout: () => {},
  }
  return (
    <AuthContext.Provider value={auth}>
      <CompanyProbe />
      <button onClick={() => setAuthenticated(true)}>Authenticate</button>
    </AuthContext.Provider>
  )
}

describe('private company query authorization boundary', () => {
  it('does not fetch private companies until login is confirmed', async () => {
    const fetchCompanies = vi.spyOn(masterDataService, 'listCompanies').mockResolvedValue([])
    try {
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Fixture />
        </QueryClientProvider>,
      )
      expect(screen.getByTestId('companies')).toHaveTextContent('0')
      expect(fetchCompanies).not.toHaveBeenCalled()
      fireEvent.click(screen.getByRole('button', { name: 'Authenticate' }))
      await waitFor(() => expect(fetchCompanies).toHaveBeenCalledTimes(1))
    } finally {
      fetchCompanies.mockRestore()
    }
  })
})
