/** Leave S4P without showing its login after a confirmed server logout.
 * Browsers cannot close user-opened tabs; about:blank is a neutral destination
 * outside the ERP. replace() avoids leaving the login in the current entry.
 */
export function exitApplication() {
  window.location.replace('about:blank')
}
