/** UI-only compatibility for the generic administrator imported from NEXORA.
 * User IDs, email, roles, audit actors, and stored names remain untouched.
 * Do not rewrite arbitrary user-entered names or business/legal identities.
 */
export function displayUserName(fullName?: string | null, email?: string | null): string {
  const trimmed = fullName?.trim() ?? ''
  if (/^administrador nexora(?: group)?$/i.test(trimmed)) return 'Administrador S4P'
  return trimmed || email?.trim() || 'Usuario'
}
