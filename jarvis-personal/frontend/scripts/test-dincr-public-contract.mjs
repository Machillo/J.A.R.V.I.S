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
for (const [legal, version] of [['terminos', '2026-09-23-v3'], ['privacidad', '2026-09-25-v4']]) {
  const html = await readFile(new URL(`${legal}/index.html`, out), 'utf8');
  assert.ok(html.includes(version), `${legal} shows version ${version}`);
  assert.match(html, /soporte@dincr\.com/);
}
// Google OAuth verification: Workspace data disclosures (access, use, transfer, protection, retention).
const privacy = await readFile(new URL('privacidad/index.html', out), 'utf8');
for (const phrase of ['gmail.readonly', 'no se envían a servicios de inteligencia artificial', 'no se usan para evaluar crédito',
  'data brokers', 'Supabase Vault', 'se revoca ante Google',
  'including the Limited Use requirements', 'The use of raw or derived user data received from Workspace APIs',
  'no utiliza proveedores de inteligencia artificial generativa', 'is not transferred to OpenAI or other generative-AI providers']) {
  assert.ok(privacy.includes(phrase), `privacy policy states: ${phrase}`);
}
assert.ok(!privacy.includes('correo e inteligencia artificial'), 'no generative-AI provider is listed');
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
// --- Launch polish: brand, links, metadata, accessibility, claims, prices, legal gate. ---
const pageFiles = [...routes.map(route => `${route ? route + '/' : ''}index.html`), '404.html'];
const pagesHtml = Object.fromEntries(await Promise.all(pageFiles.map(async file => [file, await readFile(new URL(file, out), 'utf8')])));
const builtFiles = new Set(listing.map(entry => entry.replaceAll('\\', '/')));
const home = pagesHtml['index.html'];
const text = html => html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

for (const [file, html] of Object.entries(pagesHtml)) {
  // Brand: DINCR only, never the legacy JARVIS/FINVA names or the old "J" icon.
  assert.doesNotMatch(text(html), /\bFINVA\b|\bJARVIS\b/i, `${file}: legacy product name`);
  assert.doesNotMatch(html, /favicon\.svg/, `${file}: legacy icon`);
  // Metadata.
  assert.match(html, /<title>[^<]+\| DINCR<\/title>/, `${file}: title`);
  assert.match(html, /<meta name="description" content="[^"]{50,}">/, `${file}: description`);
  assert.match(html, /<meta name="viewport" content="width=device-width,initial-scale=1">/, `${file}: viewport`);
  assert.doesNotMatch(html, /user-scalable=no|maximum-scale=1/, `${file}: zoom must stay enabled`);
  assert.match(html, /<meta property="og:title"[^>]+><meta property="og:description"[^>]+>/, `${file}: open graph`);
  assert.match(html, /<meta name="twitter:card" content="summary">/, `${file}: social card`);
  assert.match(html, /<link rel="apple-touch-icon" href="\/apple-touch-icon\.png">/, `${file}: app icon`);
  if (file !== '404.html') assert.match(html, /<meta property="og:image" content="https:\/\/dincr\.com\/og-image\.png">/, `${file}: og image`);
  // Accessibility basics.
  assert.equal((html.match(/<h1[ >]/g) || []).length, 1, `${file}: exactly one h1`);
  let previous = 1;
  for (const [, level] of html.matchAll(/<h([1-6])[ >]/g)) {
    assert.ok(Number(level) <= previous + 1, `${file}: heading level jumps to h${level}`);
    previous = Number(level);
  }
  assert.match(html, /<a class="skip" href="#contenido">/, `${file}: skip link`);
  for (const [img] of html.matchAll(/<img\b[^>]*>/g)) assert.match(img, /\balt="[^"]*"/, `${file}: img without alt`);
  for (const [img] of html.matchAll(/<img\b[^>]*>/g)) assert.match(img, /\bwidth="\d+" height="\d+"/, `${file}: img without dimensions (layout shift)`);
  // Links: internal targets exist, mail only to the official addresses, no dead store links.
  for (const [, href] of html.matchAll(/href="([^"]+)"/g)) {
    if (href.startsWith('mailto:')) assert.match(href, /^mailto:(soporte|privacidad)@dincr\.com$/, `${file}: ${href}`);
    else if (href.startsWith('https://')) assert.match(href, /^https:\/\/(dincr\.com|developers\.google\.com)\//, `${file}: unexpected external link ${href}`);
    else if (href.startsWith('#')) assert.ok(html.includes(`id="${href.slice(1)}"`), `${file}: missing anchor ${href}`);
    else if (href.startsWith('/')) {
      const [path, hash] = href.split('#');
      if (/\.(png|css)(\?|$)/.test(path)) assert.ok(builtFiles.has(path.slice(1).split('?')[0]), `${file}: missing asset ${href}`);
      else assert.ok(builtFiles.has(`${path.slice(1)}index.html`) || path === '/', `${file}: broken link ${href}`);
      if (hash) assert.ok(home.includes(`id="${hash}"`), `${file}: missing anchor ${href}`);
    } else assert.fail(`${file}: unexpected link ${href}`);
  }
  assert.doesNotMatch(html, /play\.google\.com|apps\.apple\.com|button disabled|Próximamente<\/span>/, `${file}: no placeholder store badges`);
  // No JavaScript beyond structured data, no analytics on the public site.
  assert.doesNotMatch(html.replace(/<script type="application\/ld\+json">[\s\S]*?<\/script>/g, ''), /<script/i, `${file}: scripts on the public site`);
  assert.doesNotMatch(html, /posthog-js|i\.posthog\.com|googletagmanager|google-analytics\.com|gtag\(/i, `${file}: tracking on the public site`);
}

// Claims: no generative-AI marketing, invented numbers, fake social proof or get-rich promises.
const marketing = text(pagesHtml['index.html'] + pagesHtml['precios/index.html'] + pagesHtml['seguridad/index.html']);
assert.doesNotMatch(marketing, /con IA\b|impulsad[oa] por (la )?IA|inteligencia artificial que|asistente (de )?IA|chatbot/i, 'no AI marketing claims');
assert.doesNotMatch(marketing, /\b\d[\d.,]*\s*(\+\s*)?(usuarios|clientes|descargas)\b|\d(\.\d)?\s*estrellas|testimonio|hac[eé]te rico|garantizad|sin riesgo|banco oficial|aliado oficial/i, 'no invented or misleading claims');
assert.match(marketing, /no es un banco/i, 'DINCR is not a bank');
assert.match(marketing, /no usa inteligencia artificial generativa/i, 'privacy: no generative AI');
assert.match(marketing, /no envía, modifica ni borra correos/i, 'privacy: read-only mail');
assert.match(marketing, /no se venden ni se usan para publicidad/i, 'privacy: no sale, no ads');
assert.match(home, /id="como-funciona"/);
assert.match(home, /Lanzamiento próximo en Android y iPhone/, 'pre-launch state is explicit while there are no store URLs');
assert.doesNotMatch(marketing, /\bOwner\b/, 'Owner is never a public plan');

// Prices: the landing config must match the backend price list.
const config = JSON.parse(await readFile(new URL('../landing/config.json', import.meta.url), 'utf8'));
const backendPrices = await readFile(new URL('../../backend/product_ops/service.py', import.meta.url), 'utf8');
for (const plan of ['basic', 'vip']) {
  const match = backendPrices.match(new RegExp(`"${plan}": \\{"regular": (\\d+)\\}`));
  assert.ok(match, `backend price for ${plan}`);
  assert.equal(config.pricesCRC[plan], Number(match[1]), `${plan} price matches the backend`);
  assert.ok(pagesHtml['precios/index.html'].includes(`₡${String(match[1]).replace(/\B(?=(\d{3})+(?!\d))/g, '.')}`), `${plan} price shown`);
}

// Stylesheet: responsive, reduced motion, visible focus, touch targets; cache-busted.
const css = await readFile(new URL('style.css', out), 'utf8');
assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
assert.match(css, /:focus-visible/);
assert.match(css, /@media \(min-width: 760px\)/);
assert.match(css, /min-height: 44px/);
assert.match(home, /href="\/style\.css\?v=[a-f0-9]{10}"/);

// Legal: Firebase Analytics/Crashlytics may stay in the published text only until the
// approved Privacy v5 replaces v4 (docs/legal/privacy-v5-proposal.md). Marketing pages never mention them.
const legalPy = await readFile(new URL('../../backend/auth/legal.py', import.meta.url), 'utf8');
const privacyVersion = legalPy.match(/PRIVACY_VERSION = "([^"]+)"/)[1];
assert.ok(pagesHtml['privacidad/index.html'].includes(privacyVersion), 'landing shows the backend privacy version');
if (privacyVersion !== '2026-09-25-v4') assert.doesNotMatch(pagesHtml['privacidad/index.html'], /Firebase Analytics|Crashlytics/, 'Privacy v5+ no longer lists Firebase telemetry');
for (const file of ['index.html', 'precios/index.html', 'seguridad/index.html', 'soporte/index.html', 'descargar/index.html']) {
  assert.doesNotMatch(pagesHtml[file], /Firebase|Crashlytics/, `${file}: no Firebase telemetry claims`);
}
console.log('DINCR public landing, legal, price, support and isolation contracts passed.');

// The Cloudflare Worker "dincr" deploys exactly this config (wrangler.jsonc): the static
// landing only, never the application bundle, and nothing a Preview could reach.
{
  const raw = await readFile(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const config = JSON.parse(raw.replace(/^\s*\/\/.*$/gm, '').replace(/,(\s*[}\]])/g, '$1'));
  assert.equal(config.name, 'dincr');
  assert.equal(config.assets?.directory, './landing-dist');
  assert.equal(config.assets?.not_found_handling, '404-page');
  assert.equal(config.main, undefined, 'the landing Worker has no code');
  assert.deepEqual(config.previews, {}, 'Previews get no bindings, variables or secrets');
  for (const key of ['vars', 'kv_namespaces', 'd1_databases', 'r2_buckets', 'services', 'secrets_store_secrets']) {
    assert.equal(config[key], undefined, `the landing Worker needs no ${key}`);
  }
}

