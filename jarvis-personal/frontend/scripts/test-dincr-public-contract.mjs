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
assert.match(css, /@media \(forced-colors: active\)/, 'masked icons stay visible in forced colors');
// Calm motion: no infinite animation, and animations run only under prefers-reduced-motion:
// no-preference (everywhere else the only animation value is the reduce block's `none`).
{
  assert.doesNotMatch(css, /\binfinite\b/, 'no infinite animation');
  const start = css.indexOf('@media (prefers-reduced-motion: no-preference)');
  assert.ok(start >= 0, 'entrance motion is gated by prefers-reduced-motion: no-preference');
  let depth = 0, end = css.indexOf('{', start);
  for (; end < css.length; end++) { if (css[end] === '{') depth++; else if (css[end] === '}' && --depth === 0) break; }
  const outside = css.slice(0, start) + css.slice(end + 1);
  for (const [, value] of outside.matchAll(/animation(?:-name)?\s*:\s*([^;}]+)/g)) {
    assert.match(value, /^none\b/, `animation outside prefers-reduced-motion: no-preference: ${value.trim()}`);
  }
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{[^@]*\*, \*::before, \*::after \{[^}]*animation: none !important/, 'reduce disables every animation');
}

// Colors: every landing variable names its DESIGN.md token; text and control pairs meet WCAG AA
// in both schemes; the values must not drift from DESIGN.md (DINCR 2.0 tokens, the only source).
{
  const block = source => Object.fromEntries([...source.matchAll(/--([a-z0-9-]+): (#[0-9A-Fa-f]{6}); \/\* ([a-z0-9-]+) \*\//g)].map(([, name, hex, token]) => [name, { hex, token }]));
  const lightStart = css.indexOf('@media (prefers-color-scheme: light)');
  assert.ok(lightStart > 0, 'the light scheme block exists');
  const darkSource = css.slice(0, lightStart);
  const lightSource = css.slice(lightStart, lightStart + css.slice(lightStart).search(/\n\}\r?\n/));
  const schemes = { dark: block(darkSource), light: block(lightSource) };
  // No literal color escapes the token check. Inside the scheme blocks, every declaration other
  // than a token-tagged variable is free of literal colors (the shadow's rgba and the icon masks
  // are geometry, not palette); both schemes define the same variables; the rules after the blocks
  // use only variables, `transparent` and system colors, and never redefine a token variable.
  const literalColor = /#[0-9A-Fa-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(|(?:^|[\s,(])(?:white|black|red|green|blue|gray|grey|orange|yellow|purple|pink|silver|teal|navy|gold|aqua|lime|maroon|olive|fuchsia)(?=[\s,;)!]|$)/i;
  for (const [scheme, source] of [['dark', darkSource], ['light', lightSource]]) {
    for (const [, name, value] of source.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(--[a-z0-9-]+|[a-z-]+)\s*:\s*([^;{}]+);/g)) {
      if (/^--/.test(name) && schemes[scheme][name.slice(2)] && /^#[0-9A-Fa-f]{6}$/.test(value.trim())) continue;
      if (name === '--shadow' || name.startsWith('--icon-')) continue;
      assert.doesNotMatch(value, literalColor, `${scheme}: ${name} uses a literal color; add a DESIGN.md token instead`);
    }
  }
  assert.deepEqual(Object.keys(schemes.light).sort(), Object.keys(schemes.dark).sort(), 'light and dark define the same color variables');
  const rules = css.slice(lightStart + lightSource.length).replace(/\/\*[\s\S]*?\*\//g, '');
  for (const [, name, value] of rules.matchAll(/([a-z-]+|--[a-z0-9-]+)\s*:\s*([^;{}]+)/g)) {
    assert.doesNotMatch(value, literalColor, `rules: ${name}: ${value.trim()} uses a literal color; use a token variable`);
  }
  for (const name of Object.keys(schemes.dark)) {
    assert.doesNotMatch(rules, new RegExp(`--${name}\\s*:`), `rules redefine --${name}; token variables live only in the scheme blocks`);
  }
  const luminance = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
  const ratio = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
  const layers = ['bg', 'surface', 'surface-2'];
  const pairs = [
    ...['text', 'text-2', 'muted', 'accent-text'].flatMap(fg => layers.map(bg => [fg, bg, 4.5])),
    ['on-accent', 'accent', 4.5], ['on-accent', 'accent-pressed', 4.5], ['on-accent-soft', 'accent-soft', 4.5],
    ['accent-text', 'accent-soft', 4.5], ['text', 'accent-soft', 4.5], ['vip', 'vip-soft', 4.5],
    // Non-text (WCAG 1.4.11): ghost button and chip borders, focus ring, status dot and icons.
    ...['field-border', 'accent-text', 'warning'].flatMap(fg => layers.map(bg => [fg, bg, 3])),
  ];
  // DESIGN.md is mandatory: a missing or renamed file fails here instead of skipping the check.
  const design = (await readFile(new URL('../../../DESIGN.md', import.meta.url), 'utf8')).replace(/\r\n/g, '\n');
  const token = key => design.match(new RegExp(`^  ${key}: "(#[0-9A-Fa-f]{6})"$`, 'm'))?.[1];
  for (const [scheme, vars] of Object.entries(schemes)) {
    assert.ok(Object.keys(vars).length >= 19, `${scheme}: every color variable names its DESIGN.md token`);
    for (const [fg, bg, min] of pairs) {
      const value = ratio(vars[fg].hex, vars[bg].hex);
      assert.ok(value >= min, `${scheme}: ${fg} on ${bg} is ${value.toFixed(2)}:1, needs ${min}:1`);
    }
    for (const [name, { hex, token: tokenName }] of Object.entries(vars)) {
      const key = scheme === 'dark' ? `dark-${tokenName}` : tokenName;
      const value = token(key);
      assert.ok(value, `DESIGN.md defines ${key} (landing --${name})`);
      assert.equal(hex.toUpperCase(), value.toUpperCase(), `landing --${name} (${scheme}) drifted from DESIGN.md ${key}`);
    }
  }
  // The browser chrome color follows the same background tokens on every page.
  for (const [file, html] of Object.entries(pagesHtml)) {
    assert.ok(html.includes(`<meta name="theme-color" content="${token('dark-bg')}" media="(prefers-color-scheme: dark)">`), `${file}: dark theme-color is DESIGN.md dark-bg`);
    assert.ok(html.includes(`<meta name="theme-color" content="${token('bg')}" media="(prefers-color-scheme: light)">`), `${file}: light theme-color is DESIGN.md bg`);
  }
}

// Table marks: decorative icon plus real text, not role="img" on an empty span.
assert.doesNotMatch(pagesHtml['precios/index.html'], /role="img"/);
assert.match(pagesHtml['precios/index.html'], /<span class="sr-only">Incluido<\/span>/);
assert.match(pagesHtml['precios/index.html'], /<span class="sr-only">No incluido<\/span>/);

// Download page: the published minimum OS versions (config.json `minimumOS`) must equal what the
// releasable native projects declare, whatever those values are: changing a minimum in a native
// project without updating config.json fails here, and the page follows config.json. No store
// looks available before its official URL is configured.
{
  const download = pagesHtml['descargar/index.html'];
  const gradle = await readFile(new URL('../android/variables.gradle', import.meta.url), 'utf8');
  const minSdk = Number(gradle.match(/minSdkVersion = (\d+)/)?.[1]);
  const androidRelease = { 21: '5.0', 22: '5.1', 23: '6.0', 24: '7.0', 25: '7.1', 26: '8.0', 27: '8.1', 28: '9', 29: '10', 30: '11', 31: '12', 32: '12L', 33: '13', 34: '14', 35: '15', 36: '16' }[minSdk];
  assert.ok(androidRelease, `Android minSdk ${minSdk} has no known release name: extend the table`);
  assert.equal(config.minimumOS.android, androidRelease, `Android minSdk ${minSdk} is Android ${androidRelease}: update config.json minimumOS.android`);
  assert.ok(download.includes(`Requiere Android ${androidRelease} o posterior.`), '/descargar/ states the Android minimum');
  // ios-dincr is the releasable iOS project (test:ios-identity); a native prototype elsewhere does not count.
  const pbxproj = await readFile(new URL('../ios-dincr/App/App.xcodeproj/project.pbxproj', import.meta.url), 'utf8');
  const iosTargets = [...new Set([...pbxproj.matchAll(/IPHONEOS_DEPLOYMENT_TARGET = "?([^";\s]+)"?;/g)].map(m => m[1]))];
  assert.equal(iosTargets.length, 1, `ios-dincr declares one deployment target (found ${iosTargets.join(', ') || 'none'})`);
  const iosMinimum = iosTargets[0].replace(/\.0$/, '');
  assert.equal(config.minimumOS.ios, iosMinimum, `ios-dincr targets iOS ${iosMinimum}: update config.json minimumOS.ios (release decision)`);
  assert.ok(download.includes(`Requiere iOS ${iosMinimum} o posterior.`), '/descargar/ states the iOS minimum');
  for (const [store, key] of [['Google Play', 'googlePlayUrl'], ['App Store', 'appStoreUrl']]) {
    if (config[key]) continue;
    assert.ok(download.includes(`Disponible próximamente en ${store}.`), `${store}: upcoming state is explicit`);
    assert.ok(!Object.values(pagesHtml).some(html => html.includes(`Descargar en ${store}`)), `${store}: no download button without a URL`);
  }
}
// In-app help lives in "Ayuda y soporte" ("Reportes" is the financial reports screen).
assert.match(support, /Ayuda y soporte/);
assert.doesNotMatch(support, /sección (de )?Reportes/);

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

