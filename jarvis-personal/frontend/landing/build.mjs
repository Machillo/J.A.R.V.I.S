import { readFile, writeFile, mkdir, copyFile, rm } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';

// Static, JavaScript-free public site for dincr.com (marketing, plans, legal, support).
// Every product claim here must match what DINCR does in `main`; see
// scripts/test-dincr-public-contract.mjs for the guarded claims.
const root = resolve(import.meta.dirname, '..');
const out = join(root, 'landing-dist');
const cfg = JSON.parse(await readFile(join(import.meta.dirname, 'config.json'), 'utf8'));
const base = cfg.baseUrl.replace(/\/$/, '');
if (base && !/^https:\/\/[^/]+$/.test(base)) throw Error('baseUrl must be an HTTPS origin');
for (const key of ['googlePlayUrl', 'appStoreUrl']) if (cfg[key] && !/^https:\/\//.test(cfg[key])) throw Error(`${key} must be HTTPS`);
const escape = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const url = path => base + path;
// Content hash in the stylesheet URL so a new deploy is never served a stale cached CSS.
const cssVersion = createHash('sha256').update(await readFile(join(import.meta.dirname, 'style.css'))).digest('hex').slice(0, 10);
const crc = n => `₡${String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.')}`;

const legalSource = await readFile(join(root, 'src/pages/PublicInfoPage.jsx'), 'utf8');
function legal(name) {
  const start = legalSource.indexOf(`function ${name}() {`);
  const end = legalSource.indexOf('\nexport default', start + 1);
  if (start < 0 || end < 0) throw Error(`Missing legal source ${name}`);
  const part = legalSource.slice(start, end);
  const match = part.match(/<section className="public-copy legal-copy">([\s\S]*?)<\/section>/);
  if (!match) throw Error(`Missing legal content ${name}`);
  return match[1].replace(/ target="_blank"/g, '').replace(/ rel="noreferrer"/g, '');
}
const legalVersion = (name) => legalSource.slice(legalSource.indexOf(`function ${name}() {`)).match(/VERSIÓN ([0-9]{4}-[0-9]{2}-[0-9]{2}-v[0-9]+)/)?.[1] || '';

// --- Shell -----------------------------------------------------------------------
const links = [['/#como-funciona', 'Cómo funciona'], ['/precios/', 'Planes'], ['/seguridad/', 'Seguridad'], ['/soporte/', 'Soporte']];
const navLinks = links.map(([href, label]) => `<a href="${href}">${label}</a>`).join('');
const header = `<header class="top"><div class="wrap top-row"><a class="brand" href="/" aria-label="DINCR, inicio"><img src="/apple-touch-icon.png" width="32" height="32" alt=""><span>DINCR</span></a><nav class="nav-inline" aria-label="Principal">${navLinks}</nav><details class="nav-menu"><summary aria-label="Abrir menú">Menú</summary><nav aria-label="Principal (móvil)">${navLinks}</nav></details></div></header>`;
const footer = `<footer class="site-footer"><div class="wrap footer-grid"><div class="footer-brand"><a class="brand" href="/" aria-label="DINCR, inicio"><img src="/apple-touch-icon.png" width="28" height="28" alt="" loading="lazy"><span>DINCR</span></a><p>Finanzas personales para Costa Rica. DINCR no es un banco ni una entidad financiera: no mueve tu dinero y sus cálculos son orientativos.</p></div><nav aria-label="Producto"><h2>Producto</h2><a href="/precios/">Planes</a><a href="/descargar/">Descargar</a><a href="/bancos-compatibles/">Bancos compatibles</a></nav><nav aria-label="Legal"><h2>Legal</h2><a href="/privacidad/">Privacidad</a><a href="/terminos/">Términos</a><a href="/eliminar-cuenta/">Eliminar cuenta y datos</a></nav><nav aria-label="Ayuda"><h2>Ayuda</h2><a href="/soporte/">Soporte</a><a href="/seguridad/">Seguridad</a>${cfg.supportEmail ? `<a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>` : ''}</nav></div><div class="wrap footer-legal"><small>© 2026 DINCR · Costa Rica</small></div></footer>`;
const description = 'DINCR reúne ingresos, gastos, deudas y metas en una app de finanzas personales para Costa Rica, con detección opcional de avisos bancarios en tu correo.';

function layout(path, title, content, { noindex = false, desc = description, schema = false } = {}) {
  const canonical = base && path !== '/404/' ? `<link rel="canonical" href="${escape(url(path))}"><meta property="og:url" content="${escape(url(path))}">` : '';
  const image = base ? `<meta property="og:image" content="${escape(url('/og-image.png'))}"><meta property="og:image:width" content="512"><meta property="og:image:height" content="512"><meta property="og:image:alt" content="Logotipo de DINCR"><meta name="twitter:image" content="${escape(url('/og-image.png'))}">` : '';
  const ld = schema ? `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@type': 'SoftwareApplication', name: 'DINCR', applicationCategory: 'FinanceApplication', operatingSystem: 'Android, iOS', description, inLanguage: 'es-CR', ...(base ? { url: base } : {}) }).replace(/</g, '\\u003c')}</script>` : '';
  return `<!doctype html><html lang="es-CR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)} | DINCR</title><meta name="description" content="${escape(desc)}">${noindex || !base ? '<meta name="robots" content="noindex,follow">' : ''}${canonical}<meta name="theme-color" content="#0b132b" media="(prefers-color-scheme: dark)"><meta name="theme-color" content="#f8fafc" media="(prefers-color-scheme: light)"><meta name="color-scheme" content="dark light"><meta property="og:type" content="website"><meta property="og:locale" content="es_CR"><meta property="og:site_name" content="DINCR"><meta property="og:title" content="${escape(title)} | DINCR"><meta property="og:description" content="${escape(desc)}">${image}<meta name="twitter:card" content="summary"><meta name="twitter:title" content="${escape(title)} | DINCR"><meta name="twitter:description" content="${escape(desc)}"><link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="stylesheet" href="/style.css?v=${cssVersion}">${ld}</head><body><a class="skip" href="#contenido">Saltar al contenido</a>${header}<main id="contenido">${content}</main>${footer}</body></html>`;
}

// --- Availability: real store links only when configured, never placeholder badges. ----
const storeLinks = [['Google Play', 'googlePlayUrl'], ['App Store', 'appStoreUrl']].filter(([, key]) => cfg[key]);
const availability = storeLinks.length
  ? `<div class="actions">${storeLinks.map(([label, key]) => `<a class="button" href="${escape(cfg[key])}" rel="noopener noreferrer">Descargar en ${label}</a>`).join('')}</div>`
  : `<p class="status"><span class="dot" aria-hidden="true"></span>Lanzamiento próximo en Android y iPhone. Los enlaces oficiales de descarga se publicarán aquí.</p>`;

// --- Plans (prices from config.json; checked against the backend by the contract test). ---
const plans = [
  { key: 'free', name: 'Free', pitch: 'Para ordenar lo esencial.', features: ['Ingresos y gastos por categoría', 'Resumen de tu mes', 'Deudas con saldos, cuotas y fechas', 'Metas de ahorro'] },
  { key: 'basic', name: 'Basic', pitch: 'Para planificar tu mes.', features: ['Todo lo de Free', 'Presupuesto guiado', 'Pagos recurrentes y calendario financiero', 'Estrategia básica y reportes'] },
  { key: 'vip', name: 'VIP', pitch: 'Para automatizar y proyectar.', features: ['Todo lo de Basic', 'Detección de avisos bancarios en Gmail u Outlook, con tu revisión', 'Estrategia, proyecciones, escenarios y revisión mensual', 'Estimación de aguinaldo con órdenes patronales de la CCSS'] },
];
const planCards = (level = 3) => `<div class="plans">${plans.map(p => `<article class="plan${p.key === 'vip' ? ' plan-vip' : ''}"><h${level} class="plan-name">${p.name}</h${level}><p class="plan-pitch">${p.pitch}</p><p class="price">${cfg.pricesCRC[p.key] ? `${crc(cfg.pricesCRC[p.key])}<span>/mes</span>` : 'Gratis'}</p><ul>${p.features.map(f => `<li>${f}</li>`).join('')}</ul></article>`).join('')}</div>`;
const promo = `<p class="note">Basic y VIP son gratis hasta el 31 de diciembre de 2026, sin cobro automático. Los precios mensuales indicados rigen desde enero de 2027. La compra desde Google Play y App Store estará disponible más adelante.</p>`;

// --- Home --------------------------------------------------------------------------
// A real screenshot replaces the illustration when `heroScreenshot` is configured.
const heroVisual = cfg.heroScreenshot
  ? `<figure class="hero-visual"><img class="shot" src="${escape(cfg.heroScreenshot)}" alt="Pantalla de DINCR" width="300" height="650" decoding="async"></figure>`
  : `<figure class="hero-visual"><div class="illus" aria-hidden="true"><div class="illus-card"><span class="illus-label">Aviso de tu banco detectado</span><strong>Supermercado</strong><span class="illus-amount">₡12.500</span><div class="illus-actions"><span class="chip ok">Confirmar</span><span class="chip">Corregir</span><span class="chip">Descartar</span></div></div><div class="illus-card illus-card-soft"><span class="illus-label">Este mes</span><div class="bar"><i style="width:62%"></i></div><span class="illus-note">62 % del presupuesto</span></div></div><figcaption>Ilustración con datos de ejemplo.</figcaption></figure>`;

const steps = [
  ['Registrá o conectá', 'Anotá movimientos, deudas y metas. En VIP podés conectar Gmail u Outlook, si querés.'],
  ['DINCR organiza', 'Clasifica movimientos, detecta avisos de bancos compatibles y calcula tu situación.'],
  ['Vos confirmás', 'Nada detectado en tu correo se guarda sin tu revisión: lo confirmás, corregís o descartás.'],
  ['Ves qué sigue', 'Resumen, presupuesto y estrategia con tus próximos pasos, según tu plan.'],
];
const features = [
  ['Movimientos y gastos', 'Ingresos y gastos por categoría, con un resumen claro de tu mes.', 'Free'],
  ['Deudas', 'Saldos, cuotas y fechas de pago de cada deuda en un solo lugar.', 'Free'],
  ['Metas', 'Ahorrá para objetivos concretos y seguí tu avance.', 'Free'],
  ['Presupuesto y calendario', 'Presupuesto guiado, pagos recurrentes y calendario financiero.', 'Basic'],
  ['Correos financieros', 'Detecta avisos y estados de cuenta de BAC Credomatic, Multimoney y Banco Popular en tu correo conectado.', 'VIP'],
  ['Estrategia y proyecciones', 'Prioridad recomendada, proyecciones, escenarios y revisión mensual.', 'VIP'],
];
const privacyPoints = [
  'Conectar un correo es opcional y lo podés desconectar cuando quieras.',
  'Acceso de solo lectura: DINCR no envía, modifica ni borra correos, y solo revisa remitentes financieros compatibles.',
  'Tus datos no se venden ni se usan para publicidad.',
  'DINCR no usa inteligencia artificial generativa con tus datos ni los usa para entrenar modelos.',
  'La analítica de uso es anónima y nunca incluye montos, cuentas ni el contenido de tus correos.',
  'Podés descargar una copia de tus datos y eliminar tu cuenta desde la app.',
];
const faqItems = [
  ['¿Qué es DINCR?', 'Una app móvil de finanzas personales para Costa Rica. Reúne tus ingresos, gastos, deudas y metas, y te muestra tu situación y tus próximos pasos.'],
  ['¿Tengo que conectar mi correo?', 'No. Podés usar DINCR registrando tu información. Conectar Gmail u Outlook es opcional, está disponible en VIP y requiere tu autorización explícita.'],
  ['¿DINCR lee todos mis correos?', 'No. El permiso es de solo lectura y DINCR solo busca mensajes de remitentes financieros compatibles. No envía, modifica ni borra correos. El detalle técnico usado para revisar un movimiento se elimina a los 30 días y los datos identificativos del correo a los 90, cuando no hay revisiones pendientes.'],
  ['¿Qué bancos son compatibles?', 'Hoy DINCR reconoce avisos y estados de cuenta de BAC Credomatic, Multimoney y Banco Popular, además de las órdenes patronales de la CCSS. Detectar un aviso no equivale a una conexión bancaria ni a un convenio con el banco.'],
  ['¿DINCR es un banco o mueve mi dinero?', 'No. DINCR no es un banco, no accede a tus cuentas bancarias y no ejecuta pagos ni inversiones. Sus cálculos y estrategias son orientativos.'],
  ['¿Cómo protege DINCR mis datos?', 'Tus datos viajan cifrados, se separan por cuenta y las autorizaciones de correo se guardan cifradas en el servidor. Podés proteger la app con biometría. Consultá la política de privacidad para el detalle.'],
  ['¿Puedo eliminar mi cuenta y mis datos?', 'Sí, desde la app. Al eliminar la cuenta se borran tus datos financieros y se revoca el acceso a tu correo. Antes podés descargar una copia de tus datos.'],
  ['¿Cuánto cuesta?', `Free es gratis. Basic cuesta ${crc(cfg.pricesCRC.basic)}/mes y VIP ${crc(cfg.pricesCRC.vip)}/mes, y ambos son gratis hasta el 31 de diciembre de 2026.`],
  ['¿Dónde lo descargo?', 'DINCR estará en Google Play y App Store. Los enlaces oficiales aparecerán en esta página cuando se publiquen.'],
];
const faq = faqItems.map(([q, a]) => `<details><summary>${q}</summary><p>${a}</p></details>`).join('');

const home = `<section class="hero"><div class="wrap hero-grid"><div class="hero-copy"><p class="eyebrow">Finanzas personales · Costa Rica</p><h1>Tus finanzas en orden, con menos trabajo manual.</h1><p class="lead">DINCR reúne tus ingresos, gastos, deudas y metas en una sola app y te muestra con claridad dónde estás y qué sigue.</p><p class="lead-sub">Con VIP, detecta los avisos de tu banco en tu correo para que solo tengás que confirmarlos.</p><div class="actions"><a class="button" href="#planes">Ver planes</a><a class="button button-ghost" href="#como-funciona">Cómo funciona</a></div>${availability}</div>${heroVisual}</div></section>
<section class="section problem"><div class="wrap"><p class="eyebrow">El problema</p><h2>Tu dinero está en todos lados. Tu panorama, en ninguno.</h2><ul class="pain"><li>Los avisos del banco se pierden en el correo.</li><li>Cada deuda tiene su cuota y su fecha.</li><li>Sin registro, cuesta saber cuánto podés gastar.</li></ul><p class="section-lead">DINCR lo junta en un solo lugar y lo mantiene al día.</p></div></section>
<section class="section band" id="como-funciona"><div class="wrap"><p class="eyebrow">Cómo funciona</p><h2>Vos conservás el control.</h2><ol class="steps">${steps.map(([h, p]) => `<li><h3>${h}</h3><p>${p}</p></li>`).join('')}</ol></div></section>
<section class="section" id="funciones"><div class="wrap"><p class="eyebrow">Qué incluye</p><h2>Lo que necesitás para decidir mejor.</h2><div class="features">${features.map(([h, p, plan]) => `<article class="feature"><span class="badge badge-${plan.toLowerCase()}">${plan}</span><h3>${h}</h3><p>${p}</p></article>`).join('')}</div><p class="note">La insignia indica el plan desde el que está disponible cada función.</p></div></section>
<section class="section band" id="privacidad"><div class="wrap split"><div><p class="eyebrow">Privacidad</p><h2>Tus datos financieros son tuyos.</h2><p class="section-lead">DINCR maneja información sensible. Por eso el acceso al correo es opcional, limitado y revocable.</p><div class="inline-links"><a href="/privacidad/">Política de privacidad</a><a href="/seguridad/">Seguridad</a></div></div><ul class="checks">${privacyPoints.map(p => `<li>${p}</li>`).join('')}</ul></div></section>
<section class="section" id="planes"><div class="wrap"><p class="eyebrow">Planes</p><h2>Empezá gratis. Crecé cuando lo necesités.</h2>${planCards(3)}${promo}<a class="text-link" href="/precios/">Comparar planes en detalle</a></div></section>
<section class="section band"><div class="wrap narrow"><p class="eyebrow">Preguntas frecuentes</p><h2>Lo esencial, sin letra pequeña.</h2><div class="faqs">${faq}</div></div></section>
<section class="section cta"><div class="wrap narrow center"><h2>Poné tus finanzas en orden.</h2><p class="section-lead">Empezá con Free y pasá a Basic o VIP cuando lo necesités.</p>${availability}<div class="actions center"><a class="button" href="/precios/">Ver planes</a></div></div></section>`;

// --- Pricing -----------------------------------------------------------------------
const rows = [
  ['Ingresos, gastos y resumen del mes', 1, 1, 1],
  ['Deudas con cuotas y fechas', 1, 1, 1],
  ['Metas de ahorro', 1, 1, 1],
  ['Presupuesto guiado', 0, 1, 1],
  ['Pagos recurrentes y calendario financiero', 0, 1, 1],
  ['Estrategia básica y reportes', 0, 1, 1],
  ['Detección de avisos bancarios en Gmail u Outlook', 0, 0, 1],
  ['Estrategia, proyecciones, escenarios y revisión mensual', 0, 0, 1],
  ['Estimación de aguinaldo (órdenes patronales de la CCSS)', 0, 0, 1],
];
const mark = v => v ? '<span aria-label="Incluido">✓</span>' : '<span class="muted" aria-label="No incluido">—</span>';
const comparison = `<div class="table-wrap"><table class="compare"><caption>Funciones por plan</caption><thead><tr><th scope="col">Función</th><th scope="col">Free</th><th scope="col">Basic</th><th scope="col">VIP</th></tr></thead><tbody>${rows.map(([f, ...v]) => `<tr><th scope="row">${f}</th>${v.map(x => `<td>${mark(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;

const securityPoints = [
  ['Autenticación y aislamiento', 'Cada cuenta ve solo su propia información. El acceso se valida en el servidor, no solo en la app.'],
  ['Correo con permisos mínimos', 'Gmail y Outlook se conectan con permiso de solo lectura. La autorización se guarda cifrada en el servidor y nunca se envía a la app.'],
  ['Revisión antes de guardar', 'Los movimientos detectados en el correo quedan pendientes hasta que los confirmás.'],
  ['Bloqueo de la app', 'Podés proteger DINCR con la biometría de tu teléfono.'],
  ['Control de tus datos', 'Podés descargar una copia de tus datos, desconectar tu correo y eliminar tu cuenta desde la app.'],
  ['Analítica sin contenido financiero', 'La analítica de uso es anónima: registra qué funciones se usan y qué falla, nunca montos, cuentas ni correos.'],
];

const pages = {
  '/': layout('/', 'Finanzas personales en orden', home, { schema: true }),
  '/precios/': layout('/precios/', 'Planes y precios', `<section class="section page"><div class="wrap"><p class="eyebrow">Planes</p><h1>Planes DINCR</h1><p class="section-lead">Free es gratis. Basic y VIP suman planificación y automatización.</p>${planCards(2)}${promo}${comparison}<p class="note">Confirmá el precio vigente dentro de la app antes de contratar.</p></div></section>`, { desc: `Planes de DINCR: Free gratis, Basic ${crc(cfg.pricesCRC.basic)}/mes y VIP ${crc(cfg.pricesCRC.vip)}/mes, gratis hasta el 31 de diciembre de 2026.` }),
  '/privacidad/': layout('/privacidad/', 'Política de privacidad', `<article class="section page legal"><div class="wrap narrow"><h1>Política de Privacidad</h1><p class="note">Versión vigente ${legalVersion('PrivacyPage')}. Es el mismo texto que se acepta en la aplicación.</p>${legal('PrivacyPage')}</div></article>`),
  '/terminos/': layout('/terminos/', 'Términos y condiciones', `<article class="section page legal"><div class="wrap narrow"><h1>Términos y Condiciones</h1><p class="note">Versión vigente ${legalVersion('TermsPage')}. Es el mismo texto que se acepta en la aplicación.</p>${legal('TermsPage')}</div></article>`),
  '/seguridad/': layout('/seguridad/', 'Seguridad', `<section class="section page"><div class="wrap"><p class="eyebrow">Seguridad</p><h1>Tus finanzas son tuyas.</h1><p class="section-lead">Cómo protege DINCR tu información. Ningún sistema es infalible: si encontrás un problema, avisanos en <a href="/soporte/">soporte</a>.</p><div class="features">${securityPoints.map(([h, p]) => `<article class="feature"><h2 class="h3">${h}</h2><p>${p}</p></article>`).join('')}</div><p>El detalle del tratamiento de datos está en la <a href="/privacidad/">política de privacidad</a>.</p></div></section>`, { desc: 'Cómo protege DINCR tu información: aislamiento por cuenta, correo de solo lectura, autorizaciones cifradas y control de tus datos.' }),
  '/soporte/': layout('/soporte/', 'Soporte', `<section class="section page"><div class="wrap narrow"><p class="eyebrow">Ayuda</p><h1>Soporte DINCR</h1>${cfg.supportEmail ? `<p>Para ayuda con la aplicación, escribinos a <a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>. Si ya usás DINCR, también podés escribirnos desde la sección Reportes de la app.</p>` : '<p>El canal público de soporte está pendiente de confirmación. Si ya usás la aplicación, podés contactar mediante la sección de Reportes.</p>'}${cfg.privacyEmail ? `<p>Para consultas sobre privacidad y datos personales: <a href="mailto:${escape(cfg.privacyEmail)}">${escape(cfg.privacyEmail)}</a>.</p>` : ''}<p><a href="/eliminar-cuenta/">Cómo eliminar tu cuenta y tus datos</a></p></div></section>`, { noindex: !cfg.supportEmail }),
  '/eliminar-cuenta/': layout('/eliminar-cuenta/', 'Eliminar cuenta y datos', `<section class="section page"><div class="wrap narrow"><p class="eyebrow">Tus datos</p><h1>Eliminar cuenta y datos</h1><p>Podés eliminar tu cuenta y tus datos desde la aplicación. La política de privacidad describe los plazos y las excepciones aplicables.</p><ol class="plain-steps"><li>Abrí Perfil o Más → Ajustes de cuenta y plan.</li><li>Elegí Eliminar cuenta y confirmá la solicitud.</li><li>Si querés, antes descargá una copia de tus datos desde la misma sección.</li></ol><p>Al eliminar la cuenta se borran tus datos financieros y se revoca el acceso a tu correo conectado.</p>${cfg.supportEmail ? `<p>Si no podés acceder a la app, escribí a <a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>.</p>` : '<p>El contacto público de soporte está pendiente de confirmación.</p>'}<p><a href="/privacidad/">Leer la política de privacidad</a></p></div></section>`),
  '/bancos-compatibles/': layout('/bancos-compatibles/', 'Bancos compatibles', `<section class="section page"><div class="wrap narrow"><h1>Bancos compatibles</h1><p>DINCR reconoce avisos y estados de cuenta de BAC Credomatic, Multimoney y Banco Popular, además de las órdenes patronales de la CCSS, en el correo que conectés en VIP. Detectar un aviso financiero no implica conexión directa ni convenio con un banco.</p></div></section>`, { noindex: true }),
  '/descargar/': layout('/descargar/', 'Descargar DINCR', `<section class="section page"><div class="wrap narrow"><h1>DINCR para Android y iPhone</h1>${availability}</div></section>`, { noindex: !cfg.googlePlayUrl && !cfg.appStoreUrl }),
};

await rm(out, { recursive: true, force: true }); await mkdir(out, { recursive: true });
for (const [path, html] of Object.entries(pages)) { const dir = join(out, path); await mkdir(dir, { recursive: true }); await writeFile(join(dir, 'index.html'), html); }
// Cloudflare Pages treats a site without a root 404.html as an SPA. This is a static multipage site.
await writeFile(join(out, '404.html'), layout('/404/', 'Página no encontrada', '<section class="section page"><div class="wrap narrow"><h1>Página no encontrada</h1><p>Revisá la dirección o volvé al <a href="/">inicio de DINCR</a>.</p></div></section>', { noindex: true }));
for (const [from, to] of [['favicon-32.png', 'favicon-32.png'], ['apple-touch-icon.png', 'apple-touch-icon.png'], ['dincr-icon-512.png', 'og-image.png']]) {
  await copyFile(join(root, 'public', from), join(out, to));
}
await copyFile(join(import.meta.dirname, 'style.css'), join(out, 'style.css'));
await mkdir(join(out, '.well-known'), { recursive: true });
await copyFile(
  join(import.meta.dirname, '.well-known', 'microsoft-identity-association.json'),
  join(out, '.well-known', 'microsoft-identity-association.json')
);
await writeFile(join(out, 'robots.txt'), `User-agent: *\n${base ? `Allow: /\nSitemap: ${base}/sitemap.xml` : 'Disallow: /'}\n`);
if (base) await writeFile(join(out, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${Object.keys(pages).filter(x => !['/bancos-compatibles/'].includes(x) && (cfg.supportEmail || x != '/soporte/') && (cfg.googlePlayUrl || cfg.appStoreUrl || x != '/descargar/')).map(x => `<url><loc>${escape(url(x))}</loc></url>`).join('')}</urlset>`);
console.log(`Built ${Object.keys(pages).length} static public routes in ${out}`);
