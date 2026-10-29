import { useEffect, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { authService } from '../../services/authService'
import { ApiError, clearEditCapability } from '../../services/httpClient'
import { exitApplication } from './exitApplication'
import type { CurrentUser } from '../../types/auth'
import { AuthContext, type AuthContextValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  // Any authenticated call that comes back 401 means the session is gone.
  // Drop the cached user so the router shows the login screen instead of a
  // scattered error state across every data page.
  useEffect(() => {
    const onExpired = () => {
      queryClient.setQueryData(['auth', 'me'], null)
    }
    window.addEventListener('nexora:session-expired', onExpired)
    return () => window.removeEventListener('nexora:session-expired', onExpired)
  }, [queryClient])

  const meQuery = useQuery<CurrentUser | null>({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        return await authService.me()
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return null
        }
        throw error
      }
    },
    retry: false,
  })

  const loginMutation = useMutation({
    mutationFn: authService.login,
    onSuccess: (user) => {
      queryClient.setQueryData(['auth', 'me'], user)
    },
  })

  const logoutMutation = useMutation({
    mutationFn: async () => {
      await queryClient.cancelQueries()
      return authService.logout()
    },
    onSuccess: () => {
      // The server has revoked the session and removed the HttpOnly cookie.
      // Exit the web application rather than routing back to S4P's login.
      // Keep the existing legacy storage key compatible until its migration.
      clearEditCapability()
      try {
        window.localStorage.removeItem('nexora.activeCompanyId')
      } catch {
        // Local storage can be disabled in private browsing.
      }
      // Erase cached private data before leaving, not after navigation
      // begins. This prevents a browser from retaining stale user context.
      queryClient.setQueryData(['auth', 'me'], null)
      queryClient.clear()
      // Safari cannot close a manually opened tab. Leave S4P entirely.
      exitApplication()
    },
    onError: () => {
      // Do not claim that sign-out completed if session revocation failed.
      window.alert('No se pudo confirmar el cierre de sesión. Su sesión sigue activa; intente salir nuevamente.')
    },
  })

  const value: AuthContextValue = {
    user: meQuery.data ?? null,
    isLoading: meQuery.isLoading,
    isAuthenticated: Boolean(meQuery.data),
    login: (payload) => loginMutation.mutateAsync(payload),
    loginError:
      loginMutation.error instanceof ApiError ? loginMutation.error.message : null,
    isLoggingIn: loginMutation.isPending,
    logout: () => logoutMutation.mutate(),
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
