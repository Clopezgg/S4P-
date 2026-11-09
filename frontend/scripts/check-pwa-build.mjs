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
