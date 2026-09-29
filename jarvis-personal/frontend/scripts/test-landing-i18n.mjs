// dincr.com in Spanish and English at the same URLs (landing/build.mjs).
// The language script is the one shipped in the built pages, run against a minimal DOM:
// a manual ES | EN choice wins, then a browser language starting with "es" shows Spanish,
// anything else English. The English legal texts must mirror the Spanish ones.
// Run after `npm run build:landing`.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { legalEn } from '../landing/legal-en.mjs';

const out = new URL('../landing-dist/', import.meta.url);
const page = async path => readFile(new URL(`${path}index.html`, out), 'utf8');
const pages = { '/': await page(''), '/privacidad/': await page('privacidad/'), '/terminos/': await page('terminos/') };
const block = (html, lang) => html.match(new RegExp(`<div class="l10n" lang="${lang}">([\\s\\S]*?)(?=<div class="l10n" lang="|</body>)`))[1];
const visibleText = html => html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, ' ').replace(/&[a-z#0-9]+;/gi, ' ').replace(/\s+/g, ' ').trim();
const script = pages['/'].match(/<script id="dincr-language">([\s\S]*?)<\/script>/)[1];

// --- The language script, run as a browser would run it ------------------------------
function browse(html, { languages, language, stored, storageThrows = false } = {}) {
  const attributes = Object.fromEntries([...html.match(/<html([^>]*)>/)[1].matchAll(/ ([\w-]+)="([^"]*)"/g)].map(([, k, v]) => [k, v.replace(/&amp;/g, '&')]));
  const listeners = {};
  const saved = new Map(stored ? [['dincr:language', stored]] : []);
  const meta = { content: html.match(/<meta name="description" content="([^"]*)">/)[1], setAttribute(k, v) { this[k] = v; } };
  const button = (lang, inBlock) => ({
    lang, inBlock, pressed: null, focused: false,
    getAttribute: k => (k === 'data-set-language' ? lang : null),
    setAttribute(k, v) { if (k === 'aria-pressed') this.pressed = v; },
    closest() { return this; },
    focus() { this.focused = true; },
  });
  const buttons = ['es', 'en'].flatMap(inBlock => ['es', 'en'].map(lang => button(lang, inBlock)));
  const root = {
    lang: attributes.lang,
    getAttribute: k => (k === 'lang' ? root.lang : attributes[k] ?? null),
    setAttribute: (k, v) => { attributes[k] = v; },
  };
  const document = {
    documentElement: root,
    title: html.match(/<title>([^<]*)<\/title>/)[1],
    querySelector(selector) {
      if (selector === 'meta[name="description"]') return meta;
      const twin = selector.match(/^\.l10n\[lang="(es|en)"\] \[data-set-language="(es|en)"\]$/);
      if (twin) return buttons.find(b => b.inBlock === twin[1] && b.lang === twin[2]) || null;
      throw Error(`unexpected selector ${selector}`);
    },
    querySelectorAll: selector => { assert.equal(selector, '[data-set-language]'); return buttons; },
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
  };
  const localStorage = {
    getItem: key => { if (storageThrows) throw Error('blocked'); return saved.get(key) ?? null; },
    setItem: (key, value) => { if (storageThrows) throw Error('blocked'); saved.set(key, value); },
  };
  vm.runInNewContext(script, { document, navigator: { languages, language }, localStorage, String });
  const fire = (type, event = {}) => (listeners[type] || []).forEach(fn => fn(event));
  fire('DOMContentLoaded');
  return {
    get lang() { return root.lang; },
    get dataLang() { return attributes['data-lang']; },
    get title() { return document.title; },
    get description() { return meta.content; },
    pressed: () => Object.fromEntries(buttons.map(b => [`${b.inBlock}:${b.lang}`, b.pressed])),
    click(lang, inBlock) { const target = buttons.find(b => b.lang === lang && b.inBlock === inBlock); fire('click', { target }); return buttons; },
    saved,
  };
}

const expectLanguage = (view, lang, html, why) => {
  assert.equal(view.lang, lang, `${why}: <html lang>`);
  assert.equal(view.dataLang, lang, `${why}: data-lang`);
  const titles = Object.fromEntries(['es', 'en'].map(l => [l, html.match(new RegExp(`data-title-${l}="([^"]+)"`))[1].replace(/&amp;/g, '&')]));
  assert.equal(view.title, titles[lang], `${why}: title`);
};

for (const [path, html] of Object.entries(pages)) {
  // Browser / device language.
  expectLanguage(browse(html, { language: 'es-CR' }), 'es', html, `${path} es-CR`);
  expectLanguage(browse(html, { language: 'es' }), 'es', html, `${path} es`);
  expectLanguage(browse(html, { language: 'es-419' }), 'es', html, `${path} es-419`);
  expectLanguage(browse(html, { language: 'en-US' }), 'en', html, `${path} en-US`);
  expectLanguage(browse(html, { language: 'en-GB' }), 'en', html, `${path} en-GB`);
  expectLanguage(browse(html, { language: 'en' }), 'en', html, `${path} en`);
  for (const unknown of ['fr-FR', 'pt-BR', 'zz', 'est', '', undefined]) {
    expectLanguage(browse(html, { language: unknown }), 'en', html, `${path} unknown ${unknown}`);
  }
  // navigator.languages (the user's ordered preference) comes before navigator.language.
  expectLanguage(browse(html, { languages: ['es-CR', 'en-US'], language: 'en-US' }), 'es', html, `${path} languages es first`);
  expectLanguage(browse(html, { languages: ['en-US', 'es-CR'], language: 'es-CR' }), 'en', html, `${path} languages en first`);
  // A manual choice wins over the device.
  expectLanguage(browse(html, { language: 'es-CR', stored: 'en' }), 'en', html, `${path} manual EN on a Spanish device`);
  expectLanguage(browse(html, { language: 'en-US', stored: 'es' }), 'es', html, `${path} manual ES on an English device`);
  expectLanguage(browse(html, { language: 'es-CR', stored: 'de' }), 'es', html, `${path} an invalid stored value is ignored`);
  // Storage blocked (private mode): the device language still decides, nothing breaks.
  expectLanguage(browse(html, { language: 'es-CR', storageThrows: true }), 'es', html, `${path} storage blocked`);
  // Description follows the language.
  const esView = browse(html, { language: 'es-CR' });
  assert.equal(esView.description, html.match(/data-description-es="([^"]+)"/)[1].replace(/&amp;/g, '&'), `${path}: Spanish description`);
  assert.deepEqual(esView.pressed(), { 'es:es': 'true', 'es:en': 'false', 'en:es': 'true', 'en:en': 'false' }, `${path}: selector state`);

  // The ES | EN selector: persists the choice, switches, and keeps focus on the visible selector.
  const view = browse(html, { language: 'en-US' });
  const buttons = view.click('es', 'en');
  expectLanguage(view, 'es', html, `${path} after choosing ES`);
  assert.equal(view.saved.get('dincr:language'), 'es', `${path}: choice saved`);
  assert.ok(buttons.find(b => b.inBlock === 'es' && b.lang === 'es').focused, `${path}: focus moves to the visible selector`);
  view.click('en', 'es');
  expectLanguage(view, 'en', html, `${path} after choosing EN`);
  assert.equal(view.saved.get('dincr:language'), 'en');
}

// --- Built pages ----------------------------------------------------------------------
const expected = {
  '/': { es: 'Tus finanzas en orden, con menos trabajo manual.', en: 'Your finances in order, with less manual work.', canonical: 'https://dincr.com/' },
  '/privacidad/': { es: 'Política de Privacidad', en: 'Privacy Policy', canonical: 'https://dincr.com/privacidad/' },
  '/terminos/': { es: 'Términos y Condiciones', en: 'Terms and Conditions', canonical: 'https://dincr.com/terminos/' },
};
for (const [path, html] of Object.entries(pages)) {
  const { es, en, canonical } = expected[path];
  // Same URL, both languages: html lang and content switch, the address never changes.
  assert.match(html, /^<!doctype html><html lang="en" /, `${path}: English without JavaScript`);
  assert.ok(html.includes(`<link rel="canonical" href="${canonical}">`), `${path}: canonical URL unchanged`);
  assert.ok(block(html, 'es').includes(`<h1>${es}</h1>`), `${path}: Spanish content`);
  assert.ok(block(html, 'en').includes(`<h1>${en}</h1>`), `${path}: English content`);
  for (const lang of ['es', 'en']) {
    const part = block(html, lang);
    // Links between the landing and the legal pages keep the published URLs in both languages.
    for (const href of ['/', '/privacidad/', '/terminos/', '/eliminar-cuenta/', '/soporte/']) {
      assert.ok(part.includes(`href="${href}"`), `${path} (${lang}): link to ${href}`);
    }
    assert.match(part, /<div class="lang-switch" role="group" aria-label="(Idioma|Language)"><button type="button" data-set-language="es" lang="es" aria-label="Español" aria-pressed="(true|false)">ES<\/button><button type="button" data-set-language="en" lang="en" aria-label="English" aria-pressed="(true|false)">EN<\/button><\/div>/, `${path} (${lang}): accessible ES | EN selector`);
    // No unresolved translation keys or template leftovers.
    assert.doesNotMatch(part, /undefined|\[object|\$\{|\bnull\b|\bt\(/, `${path} (${lang}): unresolved text`);
  }
}
for (const path of ['/', '/privacidad/', '/terminos/']) {
  assert.ok(block(pages[path], 'en').includes('href="/#how-it-works"') || path !== '/', 'English in-page links');
}

// --- English content is English -------------------------------------------------------
// Proper nouns, Costa Rican institutions and the Spanish terms the translation keeps on purpose.
const keptSpanish = ['Kenneth Andrés Alvarado Obando', 'Costa Rica', 'Banco Popular', 'BAC Credomatic', 'órdenes patronales', 'aguinaldo', 'Español'];
const spanishWords = /\b(el|la|los|las|de|del|que|para|con|por|una|tu|tus|sus|podés|querés|cuenta|correo|datos|política|términos|privacidad|eliminar|seguridad|soporte|planes|gratis|mes|año|también|según|más|está|son|sin|cuando|desde|hasta)\b/i;
const allPages = ['', 'precios/', 'seguridad/', 'privacidad/', 'terminos/', 'soporte/', 'eliminar-cuenta/', 'bancos-compatibles/', 'descargar/'];
for (const path of allPages) {
  const html = await page(path);
  let english = visibleText(block(html, 'en'));
  for (const kept of keptSpanish) english = english.split(kept).join(' ');
  english = english.replace(/[\w.]+@dincr\.com/g, ' '); // the official addresses (soporte@, privacidad@)
  const hit = english.match(spanishWords);
  assert.equal(hit, null, `/${path} English version shows Spanish word "${hit?.[0]}" near: ${hit ? english.slice(Math.max(0, hit.index - 60), hit.index + 60) : ''}`);
  // Every sentence of the Spanish version is absent from the English one.
  // (The Limited Use statement is English inside the Spanish text too: <p lang="en">.)
  const spanishOnly = block(html, 'es').replace(/<p lang="en">[\s\S]*?<\/p>/g, '');
  for (const sentence of visibleText(spanishOnly).split(/(?<=[.:?!])\s+/).filter(s => s.split(' ').length >= 5)) {
    assert.ok(!english.includes(sentence), `/${path}: Spanish sentence in the English version: ${sentence}`);
  }
}

// Exhaustive: no text node of a Spanish page is left untranslated in its English version,
// except names and identifiers that are the same in both languages.
const sameInBoth = new Set(['Android', 'Basic', 'DINCR', 'EN', 'ES', 'Free', 'Legal', 'Mail.Read', 'VIP', 'gmail.readonly', 'iPhone', 'privacidad@dincr.com', 'soporte@dincr.com', '© 2026 DINCR · Costa Rica']);
const textNodes = html => new Set([...html.replace(/<p lang="en">[\s\S]*?<\/p>/g, '').matchAll(/>([^<]+)</g)]
  .map(([, text]) => text.replace(/\s+/g, ' ').trim()).filter(text => /\p{L}/u.test(text)));
for (const path of allPages) {
  const html = await page(path);
  const english = textNodes(block(html, 'en'));
  const untranslated = [...textNodes(block(html, 'es'))].filter(text => english.has(text) && !sameInBoth.has(text));
  assert.deepEqual(untranslated, [], `/${path}: untranslated in the English version`);
}

// --- The English legal texts mirror the Spanish ones -----------------------------------
const source = await readFile(new URL('../src/pages/PublicInfoPage.jsx', import.meta.url), 'utf8');
for (const [name, path, facts] of [
  ['PrivacyPage', '/privacidad/', ['gmail.readonly', 'Mail.Read', 'read-only', 'does not send, modify or delete emails', 'not sold', 'data brokers', 'Supabase Vault', 'after 30 days', 'after 90 days', 'revoked with Google', 'revoke access from their Google account', 'Limited Use', 'Google API Services User Data Policy', 'download a copy of their data', '18 years', 'privacidad@dincr.com', 'soporte@dincr.com', 'Firebase Analytics and Crashlytics', 'PostHog']],
  ['TermsPage', '/terminos/', ['18 years', 'not a bank', '₡2,990', '₡4,990', 'December 31, 2026', 'January 1, 2027', 'Google Play or the App Store', 'laws of Costa Rica', 'soporte@dincr.com', 'non-waivable']],
]) {
  const version = source.slice(source.indexOf(`function ${name}() {`)).match(/VERSIÓN ([0-9-]+v\d+)/)[1];
  assert.equal(legalEn[name].version, version, `${name}: the translation is of the version in force`);
  const esBody = block(pages[path], 'es');
  const enBody = block(pages[path], 'en');
  assert.ok(enBody.includes(`Current version ${version}.`), `${name}: English page shows the version`);
  const count = (html, re) => (html.match(re) || []).length;
  assert.equal(count(enBody, /<h2>/g), count(esBody, /<h2>/g), `${name}: same number of sections`);
  assert.equal(count(enBody, /<p[ >]/g), count(esBody, /<p[ >]/g), `${name}: same number of paragraphs`);
  const hrefs = html => [...html.matchAll(/href="((?:mailto|https):[^"]+)"/g)].map(([, h]) => h).sort();
  assert.deepEqual(hrefs(enBody), hrefs(esBody), `${name}: same contacts and external links`);
  assert.deepEqual([...enBody.matchAll(/<code>([^<]+)<\/code>/g)].map(m => m[1]), [...esBody.matchAll(/<code>([^<]+)<\/code>/g)].map(m => m[1]), `${name}: same permissions named`);
  for (const fact of facts) assert.ok(visibleText(enBody).includes(fact), `${name}: English states "${fact}"`);
}
// The Limited Use paragraph is already English in the Spanish text: identical in both.
const limitedUse = html => visibleText(html.match(/<p lang="en">[\s\S]*?<\/p>/)[0]);
assert.equal(limitedUse(block(pages['/privacidad/'], 'en')), limitedUse(block(pages['/privacidad/'], 'es')), 'Limited Use statement identical');

console.log('dincr.com languages: device language, manual choice, same URLs, English legal texts mirror the Spanish ones.');
