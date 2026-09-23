import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const out = new URL('../landing-dist/', import.meta.url);
const routes = ['', 'precios', 'seguridad', 'privacidad', 'terminos', 'soporte', 'eliminar-cuenta', 'bancos-compatibles', 'descargar'];
for (const route of routes) {
  const html = await readFile(new URL(`${route ? route + '/' : ''}index.html`, out), 'utf8');
  assert.match(html, /<html lang="es-CR">/);
  assert.match(html, /<h1[ >]/);
  assert.ok(html.includes(`https://dincr.com/${route ? route + '/' : ''}`));
  assert.doesNotMatch(html, /J\.A\.R\.V\.I\.S\.|JARVIS|₡5\.990|5,990|precio candidato/i);
}
const price = await readFile(new URL('precios/index.html', out), 'utf8');
assert.match(price, /₡4\.990/);
const support = await readFile(new URL('soporte/index.html', out), 'utf8');
assert.match(support, /mailto:soporte@dincr\.com/);
assert.match(support, /mailto:privacidad@dincr\.com/);
for (const legal of ['terminos', 'privacidad']) {
  const html = await readFile(new URL(`${legal}/index.html`, out), 'utf8');
  assert.match(html, legal === 'terminos' ? /2026-09-23-v3/ : /2026-09-23-v2/);
  assert.match(html, /soporte@dincr\.com/);
}
assert.doesNotMatch(await readFile(new URL('terminos/index.html', out), 'utf8'), /SINPE/i);
const listing = await readdir(out, {recursive: true});
assert.ok(listing.includes('404.html'));
assert.ok(listing.includes('sitemap.xml'));
for (const entry of listing) {
  assert.doesNotMatch(entry, /\.env|\.js$|assets|dashboard|auth|firebase|supabase/i);
  try {
    const content = await readFile(join(fileURLToPath(out), entry), 'utf8');
    assert.doesNotMatch(content, /service_role|sb_secret_|posthog-js|render\.com|jarvisApi|\/api\/|\/auth\//i);
  } catch (error) {
    if (error.code !== 'EISDIR') throw error;
  }
}
console.log('DINCR public landing, legal, price, support and isolation contracts passed.');
