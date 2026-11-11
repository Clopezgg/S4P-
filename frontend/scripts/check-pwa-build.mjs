import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

// Validate the artifact browsers receive. Dev HTML does not run the PWA build
// transform and cannot detect a second manifest injected during production.
const dist = new URL('../dist/', import.meta.url)
const html = await readFile(new URL('index.html', dist), 'utf8')
const links = [...html.matchAll(/<link\b[^>]*>/gi)]
  .map(([tag]) => tag)
  .filter((tag) => /\brel\s*=\s*['"]manifest['"]/i.test(tag))
assert.equal(links.length, 1, 'Production HTML must expose exactly one PWA manifest')
const href = links[0].match(/\bhref\s*=\s*['"]([^'"]+)['"]/i)?.[1]
assert.equal(href, '/manifest.webmanifest', 'Use the shared first-party S4P manifest')
const manifest = JSON.parse(await readFile(new URL('manifest.webmanifest', dist), 'utf8'))
assert.equal(manifest.display, 'standalone', 'Mobile installation must remain standalone')
console.log('S4P production PWA: one manifest, existing file, standalone mode')

// The ERP is online-only. Dependency upgrades must preserve install metadata
// while keeping authenticated pages, application bundles and API data off cache.
const worker = await readFile(new URL('sw.js', dist), 'utf8')
const precache = worker.match(/\.precacheAndRoute\(\[([\s\S]*?)\]/)?.[1]
assert.ok(precache, 'Service worker must expose its generated precache list')
const urls = [...precache.matchAll(/\burl:\s*['"]([^'"]+)['"]/g)].map((match) => match[1])
for (const name of ['manifest.webmanifest', 'favicon.svg', 'pwa-icon.svg']) {
  assert.ok(urls.includes(name), `Installation metadata missing from precache: ${name}`)
}
assert.ok(urls.every((url) => !/^https?:/i.test(url) && /\.(?:svg|png|webmanifest)$/.test(url)),
  'Only first-party installation metadata/icons may be precached; never HTML, JS, CSS or API responses')
console.log('S4P service worker: installation metadata preserved; ERP bundles and API data excluded')
