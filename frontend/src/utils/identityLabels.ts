/** Use the authenticated identity supplied by FastAPI.
 * Render only the public name; never infer a different actor from client data.
 */
export function displayUserName(fullName?: string | null, email?: string | null): string {
  return fullName?.trim() || email?.trim() || 'Usuario'
}
