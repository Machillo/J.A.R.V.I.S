import { readFile, writeFile, mkdir, copyFile, rm } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { legalEn } from './legal-en.mjs';

// Static public site for dincr.com (marketing, plans, legal, support), in Spanish and English.
// Every product claim here must match what DINCR does in `main`; see
// scripts/test-dincr-public-contract.mjs for the guarded claims.
//
// Languages: every page carries its Spanish and its English version, each in its own
// `.l10n` block, at the same URL. One small inline script (languageScript) shows the
// visitor's language before the page is painted: a choice made with the ES | EN selector
// (kept in localStorage) wins; otherwise a browser language starting with "es" shows
// Spanish and anything else English. Without JavaScript the English version shows.
// scripts/test-landing-i18n.mjs checks both versions and the script.
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
const LANGUAGES = ['es', 'en'];
// The version without JavaScript, and the fallback for any browser language but Spanish.
const DEFAULT_LANGUAGE = 'en';

const legalSource = await readFile(join(root, 'src/pages/PublicInfoPage.jsx'), 'utf8');
function legalEs(name) {
  const start = legalSource.indexOf(`function ${name}() {`);
  const end = legalSource.indexOf('\nexport default', start + 1);
  if (start < 0 || end < 0) throw Error(`Missing legal source ${name}`);
  const part = legalSource.slice(start, end);
  const match = part.match(/<section className="public-copy legal-copy">([\s\S]*?)<\/section>/);
  if (!match) throw Error(`Missing legal content ${name}`);
  return match[1].replace(/ target="_blank"/g, '').replace(/ rel="noreferrer"/g, '');
}
const legalVersion = (name) => legalSource.slice(legalSource.indexOf(`function ${name}() {`)).match(/VERSIÓN ([0-9]{4}-[0-9]{2}-[0-9]{2}-v[0-9]+)/)?.[1] || '';
for (const name of ['TermsPage', 'PrivacyPage']) {
  // The English page must translate the text in force, never an older version.
  if (legalEn[name].version !== legalVersion(name)) {
    throw Error(`landing/legal-en.mjs ${name} is ${legalEn[name].version} but the Spanish text is ${legalVersion(name)}: update the translation`);
  }
}

// The only script on the public site besides structured data. No network, no storage
// other than the visitor's own language choice, no tracking.
const languageScript = `(function(){var d=document.documentElement,K="dincr:language";`
  + `function pick(){var s;try{s=localStorage.getItem(K)}catch(e){}if(s==="es"||s==="en")return s;`
  + `var p=(navigator.languages&&navigator.languages[0])||navigator.language||"";return /^es(-|$)/i.test(p)?"es":"en"}`
  + `function apply(l){d.lang=l;d.setAttribute("data-lang",l);var t=d.getAttribute("data-title-"+l);if(t)document.title=t;`
  + `var m=document.querySelector('meta[name="description"]'),x=d.getAttribute("data-description-"+l);if(m&&x)m.setAttribute("content",x);`
  + `var b=document.querySelectorAll("[data-set-language]");for(var i=0;i<b.length;i++)b[i].setAttribute("aria-pressed",String(b[i].getAttribute("data-set-language")===l))}`
  + `apply(pick());document.addEventListener("DOMContentLoaded",function(){apply(d.getAttribute("data-lang"))});`
  + `document.addEventListener("click",function(e){var b=e.target&&e.target.closest?e.target.closest("[data-set-language]"):null;if(!b)return;`
  + `var l=b.getAttribute("data-set-language");if(l!=="es"&&l!=="en")return;try{localStorage.setItem(K,l)}catch(e){}apply(l);`
  + `var f=document.querySelector('.l10n[lang="'+l+'"] [data-set-language="'+l+'"]');if(f)f.focus()})})();`;

// Everything a visitor reads, per language. t('Español', 'English'): the Spanish text is the
// original; the English one is its translation.
function site(lang) {
  const t = (es, en) => (lang === 'es' ? es : en);
  const crc = n => `₡${String(n).replace(/\B(?=(\d{3})+(?!\d))/g, t('.', ','))}`;
  const id = { content: t('contenido', 'content'), how: t('como-funciona', 'how-it-works'), features: t('funciones', 'features'), privacy: t('privacidad', 'privacy'), plans: t('planes', 'plans') };

  // --- Shell -----------------------------------------------------------------------
  const links = [[`/#${id.how}`, t('Cómo funciona', 'How it works')], ['/precios/', t('Planes', 'Plans')], ['/seguridad/', t('Seguridad', 'Security')], ['/soporte/', t('Soporte', 'Support')]];
  const navLinks = links.map(([href, label]) => `<a href="${href}">${label}</a>`).join('');
  const switcher = `<div class="lang-switch" role="group" aria-label="${t('Idioma', 'Language')}"><button type="button" data-set-language="es" lang="es" aria-label="Español" aria-pressed="${lang === 'es'}">ES</button><button type="button" data-set-language="en" lang="en" aria-label="English" aria-pressed="${lang === 'en'}">EN</button></div>`;
  const header = `<header class="top"><div class="wrap top-row"><a class="brand" href="/" aria-label="${t('DINCR, inicio', 'DINCR, home')}"><img src="/apple-touch-icon.png" width="32" height="32" alt=""><span>DINCR</span></a><nav class="nav-inline" aria-label="${t('Principal', 'Main')}">${navLinks}</nav><div class="top-actions">${switcher}<details class="nav-menu"><summary aria-label="${t('Abrir menú', 'Open menu')}">${t('Menú', 'Menu')}</summary><nav aria-label="${t('Principal (móvil)', 'Main (mobile)')}">${navLinks}</nav></details></div></div></header>`;
  const footer = `<footer class="site-footer"><div class="wrap footer-grid"><div class="footer-brand"><a class="brand" href="/" aria-label="${t('DINCR, inicio', 'DINCR, home')}"><img src="/apple-touch-icon.png" width="28" height="28" alt="" loading="lazy"><span>DINCR</span></a><p>${t('Finanzas personales para Costa Rica. DINCR no es un banco ni una entidad financiera: no mueve tu dinero y sus cálculos son orientativos.', 'Personal finance for Costa Rica. DINCR is not a bank or a financial institution: it does not move your money and its calculations are for guidance only.')}</p></div><nav aria-label="${t('Producto', 'Product')}"><h2>${t('Producto', 'Product')}</h2><a href="/precios/">${t('Planes', 'Plans')}</a><a href="/descargar/">${t('Descargar', 'Download')}</a><a href="/bancos-compatibles/">${t('Bancos compatibles', 'Supported banks')}</a></nav><nav aria-label="Legal"><h2>Legal</h2><a href="/privacidad/">${t('Privacidad', 'Privacy')}</a><a href="/terminos/">${t('Términos', 'Terms')}</a><a href="/eliminar-cuenta/">${t('Eliminar cuenta y datos', 'Delete account and data')}</a></nav><nav aria-label="${t('Ayuda', 'Help')}"><h2>${t('Ayuda', 'Help')}</h2><a href="/soporte/">${t('Soporte', 'Support')}</a><a href="/seguridad/">${t('Seguridad', 'Security')}</a>${cfg.supportEmail ? `<a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>` : ''}</nav></div><div class="wrap footer-legal"><small>© 2026 DINCR · Costa Rica</small></div></footer>`;
  const description = t('DINCR reúne ingresos, gastos, deudas y metas en una app de finanzas personales para Costa Rica, con detección opcional de avisos bancarios en tu correo.', 'DINCR brings income, expenses, debts and goals together in a personal finance app for Costa Rica, with optional detection of bank notifications in your email.');

  // --- Availability: real store links only when configured, never placeholder badges. ----
  const storeLinks = [['Google Play', 'googlePlayUrl'], ['App Store', 'appStoreUrl']].filter(([, key]) => cfg[key]);
  const availability = storeLinks.length
    ? `<div class="actions">${storeLinks.map(([label, key]) => `<a class="button" href="${escape(cfg[key])}" rel="noopener noreferrer">${t(`Descargar en ${label}`, `Download on ${label}`)}</a>`).join('')}</div>`
    : `<p class="status"><span class="dot" aria-hidden="true"></span>${t('Lanzamiento próximo en Android y iPhone. Los enlaces oficiales de descarga se publicarán aquí.', 'Coming soon to Android and iPhone. The official download links will be published here.')}</p>`;

  // --- Platforms: what each app offers today; the store link appears only when configured. ---
  // Minimum OS versions come from config.json; `test:landing` checks them against the native projects.
  const platforms = [
    ['Android', 'googlePlayUrl', 'Google Play', [t('Entrás con tu cuenta de Google.', 'You sign in with your Google account.'), t('Bloqueo con la biometría del teléfono (como la huella) o con su PIN, patrón o contraseña.', 'Lock with the phone’s biometrics (such as your fingerprint) or with its PIN, pattern or password.'), t(`Requiere Android ${escape(cfg.minimumOS.android)} o posterior.`, `Requires Android ${escape(cfg.minimumOS.android)} or later.`)]],
    ['iPhone', 'appStoreUrl', 'App Store', [t('Entrás con tu cuenta de Google o de Apple.', 'You sign in with your Google or Apple account.'), t('Bloqueo con Face ID, Touch ID o el código del iPhone.', 'Lock with Face ID, Touch ID or the iPhone passcode.'), t(`Requiere iOS ${escape(cfg.minimumOS.ios)} o posterior.`, `Requires iOS ${escape(cfg.minimumOS.ios)} or later.`)]],
  ].map(([name, key, store, facts]) => `<article class="platform"><h2 class="h3">${name}</h2><ul>${facts.map(f => `<li>${f}</li>`).join('')}</ul>${cfg[key] ? `<a class="button" href="${escape(cfg[key])}" rel="noopener noreferrer">${t(`Descargar en ${store}`, `Download on ${store}`)}</a>` : `<p class="note">${t(`Disponible próximamente en ${store}.`, `Coming soon to ${store}.`)}</p>`}</article>`).join('');

  // --- Plans (prices from config.json; checked against the backend by the contract test). ---
  const plans = [
    { key: 'free', name: 'Free', pitch: t('Para ordenar lo esencial.', 'To organize the essentials.'), features: [t('Ingresos y gastos por categoría', 'Income and expenses by category'), t('Resumen de tu mes', 'Summary of your month'), t('Deudas con saldos, cuotas y fechas', 'Debts with balances, installments and dates'), t('Metas de ahorro', 'Savings goals')] },
    { key: 'basic', name: 'Basic', pitch: t('Para planificar tu mes.', 'To plan your month.'), features: [t('Todo lo de Free', 'Everything in Free'), t('Presupuesto guiado', 'Guided budget'), t('Pagos recurrentes y calendario financiero', 'Recurring payments and financial calendar'), t('Estrategia básica y reportes', 'Basic strategy and reports')] },
    { key: 'vip', name: 'VIP', pitch: t('Para automatizar y proyectar.', 'To automate and project.'), features: [t('Todo lo de Basic', 'Everything in Basic'), t('Detección de avisos bancarios en Gmail u Outlook, con tu revisión', 'Detection of bank notifications in Gmail or Outlook, with your review'), t('Estrategia, proyecciones, escenarios y revisión mensual', 'Strategy, projections, scenarios and monthly review'), t('Estimación de aguinaldo con órdenes patronales de la CCSS', 'Aguinaldo (year-end bonus) estimate from CCSS employer payroll statements')] },
  ];
  const planCards = (level = 3) => `<div class="plans">${plans.map(p => `<article class="plan${p.key === 'vip' ? ' plan-vip' : ''}"><h${level} class="plan-name">${p.name}</h${level}><p class="plan-pitch">${p.pitch}</p><p class="price">${cfg.pricesCRC[p.key] ? `${crc(cfg.pricesCRC[p.key])}<span>${t('/mes', '/month')}</span>` : t('Gratis', 'Free')}</p><ul>${p.features.map(f => `<li>${f}</li>`).join('')}</ul></article>`).join('')}</div>`;
  const promo = `<p class="note">${t('Basic y VIP son gratis hasta el 31 de diciembre de 2026, sin cobro automático. Los precios mensuales indicados rigen desde enero de 2027. La compra desde Google Play y App Store estará disponible más adelante.', 'Basic and VIP are free until December 31, 2026, with no automatic charge. The monthly prices shown apply from January 2027. Purchasing through Google Play and the App Store will be available later.')}</p>`;

  // --- Home --------------------------------------------------------------------------
  // A real screenshot replaces the illustration when `heroScreenshot` is configured.
  const heroVisual = cfg.heroScreenshot
    ? `<figure class="hero-visual"><img class="shot" src="${escape(cfg.heroScreenshot)}" alt="${t('Pantalla de DINCR', 'DINCR screen')}" width="300" height="650" decoding="async"></figure>`
    : `<figure class="hero-visual"><div class="illus" aria-hidden="true"><div class="illus-card"><span class="illus-label">${t('Aviso de tu banco detectado', 'Notification from your bank detected')}</span><div class="illus-row"><strong>${t('Supermercado', 'Supermarket')}</strong><span class="illus-amount">−${crc(12500)}</span></div><div class="illus-actions"><span class="chip ok">${t('Confirmar', 'Confirm')}</span><span class="chip">${t('Corregir', 'Correct')}</span><span class="chip">${t('Descartar', 'Discard')}</span></div></div><div class="illus-card illus-card-soft"><span class="illus-label">${t('Presupuesto de este mes', 'This month’s budget')}</span><div class="bar"><i style="width:62%"></i></div><span class="illus-note">${t('62 % usado', '62% used')}</span></div></div><figcaption>${t('Ilustración con datos de ejemplo.', 'Illustration with sample data.')}</figcaption></figure>`;

  const steps = [
    [t('Registrá o conectá', 'Record or connect'), t('Anotá movimientos, deudas y metas. En VIP podés conectar Gmail u Outlook, si querés.', 'Enter transactions, debts and goals. With VIP you can connect Gmail or Outlook, if you want.')],
    [t('DINCR organiza', 'DINCR organizes'), t('Clasifica movimientos, detecta avisos de bancos compatibles y calcula tu situación.', 'It categorizes transactions, detects notifications from supported banks and works out where you stand.')],
    [t('Vos confirmás', 'You confirm'), t('Nada detectado en tu correo se guarda sin tu revisión: lo confirmás, corregís o descartás.', 'Nothing detected in your email is saved without your review: you confirm, correct or discard it.')],
    [t('Ves qué sigue', 'You see what’s next'), t('Resumen, presupuesto y estrategia con tus próximos pasos, según tu plan.', 'Summary, budget and strategy with your next steps, depending on your plan.')],
  ];
  const features = [
    [t('Movimientos y gastos', 'Transactions and expenses'), t('Ingresos y gastos por categoría, con un resumen claro de tu mes.', 'Income and expenses by category, with a clear summary of your month.'), 'Free'],
    [t('Deudas', 'Debts'), t('Saldos, cuotas y fechas de pago de cada deuda en un solo lugar.', 'Balances, installments and payment dates for every debt in one place.'), 'Free'],
    [t('Metas', 'Goals'), t('Ahorrá para objetivos concretos y seguí tu avance.', 'Save for specific goals and follow your progress.'), 'Free'],
    [t('Presupuesto y calendario', 'Budget and calendar'), t('Presupuesto guiado, pagos recurrentes y calendario financiero.', 'Guided budget, recurring payments and financial calendar.'), 'Basic'],
    [t('Correos financieros', 'Financial emails'), t('Detecta avisos y estados de cuenta de BAC Credomatic, Multimoney y Banco Popular en tu correo conectado.', 'Detects notifications and account statements from BAC Credomatic, Multimoney and Banco Popular in your connected email.'), 'VIP'],
    [t('Estrategia y proyecciones', 'Strategy and projections'), t('Prioridad recomendada, proyecciones, escenarios y revisión mensual.', 'Recommended priority, projections, scenarios and monthly review.'), 'VIP'],
  ];
  const privacyPoints = [
    t('Conectar un correo es opcional y lo podés desconectar cuando quieras.', 'Connecting an email account is optional, and you can disconnect it whenever you want.'),
    t('Acceso de solo lectura: DINCR no envía, modifica ni borra correos, y solo revisa remitentes financieros compatibles.', 'Read-only access: DINCR does not send, modify or delete emails, and it only reviews supported financial senders.'),
    t('Tus datos no se venden ni se usan para publicidad.', 'Your data is not sold or used for advertising.'),
    t('DINCR no usa inteligencia artificial generativa con tus datos ni los usa para entrenar modelos.', 'DINCR does not use generative artificial intelligence with your data and does not use it to train models.'),
    t('La analítica de uso es anónima y nunca incluye montos, cuentas ni el contenido de tus correos.', 'Usage analytics are anonymous and never include amounts, accounts or the content of your emails.'),
    t('Podés descargar una copia de tus datos y eliminar tu cuenta desde la app.', 'You can download a copy of your data and delete your account from the app.'),
  ];
  const faqItems = [
    [t('¿Qué es DINCR?', 'What is DINCR?'), t('Una app móvil de finanzas personales para Costa Rica. Reúne tus ingresos, gastos, deudas y metas, y te muestra tu situación y tus próximos pasos.', 'A mobile personal finance app for Costa Rica. It brings together your income, expenses, debts and goals, and shows you where you stand and your next steps.')],
    [t('¿Tengo que conectar mi correo?', 'Do I have to connect my email?'), t('No. Podés usar DINCR registrando tu información. Conectar Gmail u Outlook es opcional, está disponible en VIP y requiere tu autorización explícita.', 'No. You can use DINCR by entering your information. Connecting Gmail or Outlook is optional, is available with VIP and requires your explicit authorization.')],
    [t('¿DINCR lee todos mis correos?', 'Does DINCR read all my emails?'), t('No. El permiso es de solo lectura y DINCR solo busca mensajes de remitentes financieros compatibles. No envía, modifica ni borra correos. El detalle técnico usado para revisar un movimiento se elimina a los 30 días y los datos identificativos del correo a los 90, cuando no hay revisiones pendientes.', 'No. The permission is read-only and DINCR only looks for messages from supported financial senders. It does not send, modify or delete emails. The technical detail used to review a transaction is deleted after 30 days and the email’s identifying data after 90, when there are no pending reviews.')],
    [t('¿Qué bancos son compatibles?', 'Which banks are supported?'), t('Hoy DINCR reconoce avisos y estados de cuenta de BAC Credomatic, Multimoney y Banco Popular, además de las órdenes patronales de la CCSS. Detectar un aviso no equivale a una conexión bancaria ni a un convenio con el banco.', 'Today DINCR recognizes notifications and account statements from BAC Credomatic, Multimoney and Banco Popular, as well as CCSS employer payroll statements. Detecting a notification is not a bank connection or an agreement with the bank.')],
    [t('¿DINCR es un banco o mueve mi dinero?', 'Is DINCR a bank, or does it move my money?'), t('No. DINCR no es un banco, no accede a tus cuentas bancarias y no ejecuta pagos ni inversiones. Sus cálculos y estrategias son orientativos.', 'No. DINCR is not a bank, does not access your bank accounts and does not make payments or investments. Its calculations and strategies are for guidance only.')],
    [t('¿Cómo protege DINCR mis datos?', 'How does DINCR protect my data?'), t('Tus datos viajan cifrados, se separan por cuenta y las autorizaciones de correo se guardan cifradas en el servidor. Podés proteger la app con biometría. Consultá la política de privacidad para el detalle.', 'Your data travels encrypted and is separated by account, and email authorizations are stored encrypted on the server. You can protect the app with biometrics. See the privacy policy for details.')],
    [t('¿Puedo eliminar mi cuenta y mis datos?', 'Can I delete my account and my data?'), t('Sí, desde la app. Al eliminar la cuenta se borran tus datos financieros y se revoca el acceso a tu correo. Antes podés descargar una copia de tus datos.', 'Yes, from the app. Deleting the account deletes your financial data and revokes access to your email. Before that, you can download a copy of your data.')],
    [t('¿Cuánto cuesta?', 'How much does it cost?'), t(`Free es gratis. Basic cuesta ${crc(cfg.pricesCRC.basic)}/mes y VIP ${crc(cfg.pricesCRC.vip)}/mes, y ambos son gratis hasta el 31 de diciembre de 2026.`, `Free is free. Basic costs ${crc(cfg.pricesCRC.basic)}/month and VIP ${crc(cfg.pricesCRC.vip)}/month, and both are free until December 31, 2026.`)],
    [t('¿Dónde lo descargo?', 'Where do I download it?'), t('DINCR estará en Google Play y App Store. Los enlaces oficiales aparecerán en esta página cuando se publiquen.', 'DINCR will be on Google Play and the App Store. The official links will appear on this page when they are published.')],
  ];
  const faq = faqItems.map(([q, a]) => `<details><summary>${q}</summary><p>${a}</p></details>`).join('');

  const home = `<section class="hero"><div class="wrap hero-grid"><div class="hero-copy"><h1>${t('Tus finanzas en orden, con menos trabajo manual.', 'Your finances in order, with less manual work.')}</h1><p class="lead">${t('DINCR es la app de finanzas personales para Costa Rica: reúne tus ingresos, gastos, deudas y metas y te muestra con claridad dónde estás y qué sigue.', 'DINCR is the personal finance app for Costa Rica: it brings together your income, expenses, debts and goals and shows you clearly where you stand and what comes next.')}</p><p class="lead-sub">${t('Con VIP, detecta los avisos de tu banco en tu correo para que solo tengás que confirmarlos.', 'With VIP, it detects your bank’s notifications in your email so all you have to do is confirm them.')}</p><div class="actions"><a class="button" href="#${id.plans}">${t('Ver planes', 'See plans')}</a><a class="button button-ghost" href="#${id.how}">${t('Cómo funciona', 'How it works')}</a></div>${availability}</div>${heroVisual}</div></section>
<section class="section problem"><div class="wrap"><h2>${t('Tu dinero está en todos lados. Tu panorama, en ninguno.', 'Your money is everywhere. Your overview is nowhere.')}</h2><ul class="pain"><li>${t('Los avisos del banco se pierden en el correo.', 'Bank notifications get lost in your inbox.')}</li><li>${t('Cada deuda tiene su cuota y su fecha.', 'Every debt has its own installment and due date.')}</li><li>${t('Sin registro, cuesta saber cuánto podés gastar.', 'Without a record, it’s hard to know how much you can spend.')}</li></ul><p class="section-lead">${t('DINCR lo junta en un solo lugar y lo mantiene al día.', 'DINCR brings it together in one place and keeps it up to date.')}</p></div></section>
<section class="section band" id="${id.how}"><div class="wrap"><h2>${t('Vos conservás el control.', 'You stay in control.')}</h2><ol class="steps">${steps.map(([h, p]) => `<li><h3>${h}</h3><p>${p}</p></li>`).join('')}</ol></div></section>
<section class="section" id="${id.features}"><div class="wrap"><h2>${t('Lo que necesitás para decidir mejor.', 'What you need to make better decisions.')}</h2><div class="features">${features.map(([h, p, plan]) => `<article class="feature"><span class="badge badge-${plan.toLowerCase()}">${plan}</span><h3>${h}</h3><p>${p}</p></article>`).join('')}</div><p class="note">${t('La insignia indica el plan desde el que está disponible cada función.', 'The badge shows the plan from which each feature is available.')}</p></div></section>
<section class="section band" id="${id.privacy}"><div class="wrap split"><div><h2>${t('Tus datos financieros son tuyos.', 'Your financial data is yours.')}</h2><p class="section-lead">${t('DINCR maneja información sensible. Por eso el acceso al correo es opcional, limitado y revocable.', 'DINCR handles sensitive information. That is why email access is optional, limited and revocable.')}</p><div class="inline-links"><a href="/privacidad/">${t('Política de privacidad', 'Privacy policy')}</a><a href="/seguridad/">${t('Seguridad', 'Security')}</a></div></div><ul class="checks">${privacyPoints.map(p => `<li>${p}</li>`).join('')}</ul></div></section>
<section class="section" id="${id.plans}"><div class="wrap"><h2>${t('Empezá gratis. Crecé cuando lo necesités.', 'Start free. Grow when you need to.')}</h2>${planCards(3)}${promo}<a class="text-link" href="/precios/">${t('Comparar planes en detalle', 'Compare plans in detail')}</a></div></section>
<section class="section band"><div class="wrap narrow"><h2>${t('Lo esencial, sin letra pequeña.', 'The essentials, with no fine print.')}</h2><div class="faqs">${faq}</div></div></section>
<section class="section cta"><div class="wrap narrow center"><h2>${t('Poné tus finanzas en orden.', 'Put your finances in order.')}</h2><p class="section-lead">${t('Empezá con Free y pasá a Basic o VIP cuando lo necesités.', 'Start with Free and move to Basic or VIP when you need to.')}</p>${availability}<div class="actions center"><a class="button" href="/precios/">${t('Ver planes', 'See plans')}</a></div></div></section>`;

  // --- Pricing -----------------------------------------------------------------------
  const rows = [
    [t('Ingresos, gastos y resumen del mes', 'Income, expenses and monthly summary'), 1, 1, 1],
    [t('Deudas con cuotas y fechas', 'Debts with installments and dates'), 1, 1, 1],
    [t('Metas de ahorro', 'Savings goals'), 1, 1, 1],
    [t('Presupuesto guiado', 'Guided budget'), 0, 1, 1],
    [t('Pagos recurrentes y calendario financiero', 'Recurring payments and financial calendar'), 0, 1, 1],
    [t('Estrategia básica y reportes', 'Basic strategy and reports'), 0, 1, 1],
    [t('Detección de avisos bancarios en Gmail u Outlook', 'Detection of bank notifications in Gmail or Outlook'), 0, 0, 1],
    [t('Estrategia, proyecciones, escenarios y revisión mensual', 'Strategy, projections, scenarios and monthly review'), 0, 0, 1],
    [t('Estimación de aguinaldo (órdenes patronales de la CCSS)', 'Aguinaldo (year-end bonus) estimate (CCSS employer payroll statements)'), 0, 0, 1],
  ];
  // Visible marks are decorative; the cell's accessible text is the visually hidden word.
  const mark = v => v ? `<span class="yes" aria-hidden="true"></span><span class="sr-only">${t('Incluido', 'Included')}</span>` : `<span class="muted" aria-hidden="true">—</span><span class="sr-only">${t('No incluido', 'Not included')}</span>`;
  const comparison = `<div class="table-wrap"><table class="compare"><caption>${t('Funciones por plan', 'Features by plan')}</caption><thead><tr><th scope="col">${t('Función', 'Feature')}</th><th scope="col">Free</th><th scope="col">Basic</th><th scope="col">VIP</th></tr></thead><tbody>${rows.map(([f, ...v]) => `<tr><th scope="row">${f}</th>${v.map(x => `<td>${mark(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;

  const securityPoints = [
    [t('Autenticación y aislamiento', 'Authentication and isolation'), t('Cada cuenta ve solo su propia información. El acceso se valida en el servidor, no solo en la app.', 'Each account sees only its own information. Access is validated on the server, not only in the app.')],
    [t('Correo con permisos mínimos', 'Email with minimal permissions'), t('Gmail y Outlook se conectan con permiso de solo lectura. La autorización se guarda cifrada en el servidor y nunca se envía a la app.', 'Gmail and Outlook are connected with read-only permission. The authorization is stored encrypted on the server and is never sent to the app.')],
    [t('Revisión antes de guardar', 'Review before saving'), t('Los movimientos detectados en el correo quedan pendientes hasta que los confirmás.', 'Transactions detected in your email stay pending until you confirm them.')],
    [t('Bloqueo de la app', 'App lock'), t('Podés proteger DINCR con la biometría de tu teléfono.', 'You can protect DINCR with your phone’s biometrics.')],
    [t('Control de tus datos', 'Control of your data'), t('Podés descargar una copia de tus datos, desconectar tu correo y eliminar tu cuenta desde la app.', 'You can download a copy of your data, disconnect your email and delete your account from the app.')],
    [t('Analítica sin contenido financiero', 'Analytics without financial content'), t('La analítica de uso es anónima: registra qué funciones se usan y qué falla, nunca montos, cuentas ni correos.', 'Usage analytics are anonymous: they record which features are used and what fails, never amounts, accounts or emails.')],
  ];

  const legalPage = (name, esTitle) => {
    const version = legalVersion(name);
    const note = t(`Versión vigente ${version}. Es el mismo texto que se acepta en la aplicación.`, `Current version ${version}. English translation of the Spanish text accepted in the app.`);
    return `<article class="section page legal"><div class="wrap narrow"><h1>${t(esTitle, legalEn[name].title)}</h1><p class="note">${note}</p>${lang === 'es' ? legalEs(name) : legalEn[name].html}</div></article>`;
  };

  const pages = {
    '/': [t('Finanzas personales en orden', 'Personal finances in order'), home, { schema: true }],
    '/precios/': [t('Planes y precios', 'Plans and prices'), `<section class="section page"><div class="wrap"><h1>${t('Planes DINCR', 'DINCR plans')}</h1><p class="section-lead">${t('Free es gratis. Basic y VIP suman planificación y automatización.', 'Free is free. Basic and VIP add planning and automation.')}</p>${planCards(2)}${promo}${comparison}<p class="note">${t('Confirmá el precio vigente dentro de la app antes de contratar.', 'Check the current price in the app before subscribing.')}</p></div></section>`, { desc: t(`Planes de DINCR: Free gratis, Basic ${crc(cfg.pricesCRC.basic)}/mes y VIP ${crc(cfg.pricesCRC.vip)}/mes, gratis hasta el 31 de diciembre de 2026.`, `DINCR plans: Free at no cost, Basic ${crc(cfg.pricesCRC.basic)}/month and VIP ${crc(cfg.pricesCRC.vip)}/month, free until December 31, 2026.`) }],
    '/privacidad/': [t('Política de privacidad', 'Privacy policy'), legalPage('PrivacyPage', 'Política de Privacidad')],
    '/terminos/': [t('Términos y condiciones', 'Terms and conditions'), legalPage('TermsPage', 'Términos y Condiciones')],
    '/seguridad/': [t('Seguridad', 'Security'), `<section class="section page"><div class="wrap"><h1>${t('Tus finanzas son tuyas.', 'Your finances are yours.')}</h1><p class="section-lead">${t('Cómo protege DINCR tu información. Ningún sistema es infalible: si encontrás un problema, avisanos en <a href="/soporte/">soporte</a>.', 'How DINCR protects your information. No system is infallible: if you find a problem, let us know through <a href="/soporte/">support</a>.')}</p><div class="features">${securityPoints.map(([h, p]) => `<article class="feature"><h2 class="h3">${h}</h2><p>${p}</p></article>`).join('')}</div><p>${t('El detalle del tratamiento de datos está en la <a href="/privacidad/">política de privacidad</a>.', 'The details of how data is processed are in the <a href="/privacidad/">privacy policy</a>.')}</p></div></section>`, { desc: t('Cómo protege DINCR tu información: aislamiento por cuenta, correo de solo lectura, autorizaciones cifradas y control de tus datos.', 'How DINCR protects your information: isolation by account, read-only email, encrypted authorizations and control of your data.') }],
    '/soporte/': [t('Soporte', 'Support'), `<section class="section page"><div class="wrap narrow"><h1>${t('Soporte DINCR', 'DINCR support')}</h1>${cfg.supportEmail ? `<p>${t(`Para ayuda con la aplicación, escribinos a <a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>. Si ya usás DINCR, también podés escribirnos desde la sección Ayuda y soporte de la app.`, `For help with the app, write to us at <a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>. If you already use DINCR, you can also write to us from the Help and support section of the app.`)}</p>` : `<p>${t('El canal público de soporte está pendiente de confirmación. Si ya usás la aplicación, podés contactar desde la sección Ayuda y soporte de la app.', 'The public support channel is pending confirmation. If you already use the app, you can get in touch from the Help and support section of the app.')}</p>`}${cfg.privacyEmail ? `<p>${t('Para consultas sobre privacidad y datos personales:', 'For questions about privacy and personal data:')} <a href="mailto:${escape(cfg.privacyEmail)}">${escape(cfg.privacyEmail)}</a>.</p>` : ''}<p><a href="/eliminar-cuenta/">${t('Cómo eliminar tu cuenta y tus datos', 'How to delete your account and your data')}</a></p></div></section>`, { noindex: !cfg.supportEmail }],
    '/eliminar-cuenta/': [t('Eliminar cuenta y datos', 'Delete account and data'), `<section class="section page"><div class="wrap narrow"><h1>${t('Eliminar cuenta y datos', 'Delete account and data')}</h1><p>${t('Podés eliminar tu cuenta y tus datos desde la aplicación. La política de privacidad describe los plazos y las excepciones aplicables.', 'You can delete your account and your data from the app. The privacy policy describes the applicable time frames and exceptions.')}</p><ol class="plain-steps"><li>${t('Abrí Perfil o Más → Ajustes de cuenta y plan.', 'Open Profile or More → Account and plan settings.')}</li><li>${t('Elegí Eliminar cuenta y confirmá la solicitud.', 'Choose Delete account and confirm the request.')}</li><li>${t('Si querés, antes descargá una copia de tus datos desde la misma sección.', 'If you want, first download a copy of your data from the same section.')}</li></ol><p>${t('Al eliminar la cuenta se borran tus datos financieros y se revoca el acceso a tu correo conectado.', 'Deleting the account deletes your financial data and revokes access to your connected email.')}</p>${cfg.supportEmail ? `<p>${t(`Si no podés acceder a la app, escribí a <a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>.`, `If you cannot access the app, write to <a href="mailto:${escape(cfg.supportEmail)}">${escape(cfg.supportEmail)}</a>.`)}</p>` : `<p>${t('El contacto público de soporte está pendiente de confirmación.', 'The public support contact is pending confirmation.')}</p>`}<p><a href="/privacidad/">${t('Leer la política de privacidad', 'Read the privacy policy')}</a></p></div></section>`],
    '/bancos-compatibles/': [t('Bancos compatibles', 'Supported banks'), `<section class="section page"><div class="wrap narrow"><h1>${t('Bancos compatibles', 'Supported banks')}</h1><p>${t('DINCR reconoce avisos y estados de cuenta de BAC Credomatic, Multimoney y Banco Popular, además de las órdenes patronales de la CCSS, en el correo que conectés en VIP. Detectar un aviso financiero no implica conexión directa ni convenio con un banco.', 'DINCR recognizes notifications and account statements from BAC Credomatic, Multimoney and Banco Popular, as well as CCSS employer payroll statements, in the email you connect with VIP. Detecting a financial notification does not imply a direct connection or an agreement with a bank.')}</p></div></section>`, { noindex: true }],
    '/descargar/': [t('Descargar DINCR', 'Download DINCR'), `<section class="section page"><div class="wrap"><h1>${t('DINCR para Android y iPhone', 'DINCR for Android and iPhone')}</h1><p class="section-lead">${t('Si entrás con la misma cuenta en los dos sistemas, ves la misma información y el mismo plan.', 'If you sign in with the same account on both systems, you see the same information and the same plan.')}</p>${availability}<div class="platforms">${platforms}</div></div></section>`, { noindex: !cfg.googlePlayUrl && !cfg.appStoreUrl }],
    '/404/': [t('Página no encontrada', 'Page not found'), `<section class="section page"><div class="wrap narrow"><h1>${t('Página no encontrada', 'Page not found')}</h1><p>${t('Revisá la dirección o volvé al <a href="/">inicio de DINCR</a>.', 'Check the address or go back to the <a href="/">DINCR home page</a>.')}</p></div></section>`, { noindex: true }],
  };
  const body = path => {
    const [, content] = pages[path];
    return `<div class="l10n" lang="${lang}"><a class="skip" href="#${id.content}">${t('Saltar al contenido', 'Skip to content')}</a>${header}<main id="${id.content}">${content}</main>${footer}</div>`;
  };
  return { pages, body, description, ogImageAlt: t('Logotipo de DINCR', 'DINCR logo') };
}

const sites = Object.fromEntries(LANGUAGES.map(lang => [lang, site(lang)]));

function layout(path) {
  const main = sites[DEFAULT_LANGUAGE];
  const [title, , { noindex = false, desc, schema = false } = {}] = main.pages[path];
  const titleOf = lang => `${sites[lang].pages[path][0]} | DINCR`;
  const descOf = lang => sites[lang].pages[path][2]?.desc || sites[lang].description;
  const description = desc || main.description;
  const canonical = base && path !== '/404/' ? `<link rel="canonical" href="${escape(url(path))}"><meta property="og:url" content="${escape(url(path))}">` : '';
  const image = base ? `<meta property="og:image" content="${escape(url('/og-image.png'))}"><meta property="og:image:width" content="512"><meta property="og:image:height" content="512"><meta property="og:image:alt" content="${escape(main.ogImageAlt)}"><meta name="twitter:image" content="${escape(url('/og-image.png'))}">` : '';
  const ld = schema ? `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@type': 'SoftwareApplication', name: 'DINCR', applicationCategory: 'FinanceApplication', operatingSystem: 'Android, iOS', description: sites.es.description, inLanguage: ['es-CR', 'en'], ...(base ? { url: base } : {}) }).replace(/</g, '\\u003c')}</script>` : '';
  const perLanguage = LANGUAGES.map(lang => ` data-title-${lang}="${escape(titleOf(lang))}" data-description-${lang}="${escape(descOf(lang))}"`).join('');
  return `<!doctype html><html lang="${DEFAULT_LANGUAGE}"${perLanguage}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><script id="dincr-language">${languageScript}</script><title>${escape(title)} | DINCR</title><meta name="description" content="${escape(description)}">${noindex || !base ? '<meta name="robots" content="noindex,follow">' : ''}${canonical}<meta name="theme-color" content="#0A1220" media="(prefers-color-scheme: dark)"><meta name="theme-color" content="#F5F7FA" media="(prefers-color-scheme: light)"><meta name="color-scheme" content="dark light"><meta property="og:type" content="website"><meta property="og:locale" content="en_US"><meta property="og:locale:alternate" content="es_CR"><meta property="og:site_name" content="DINCR"><meta property="og:title" content="${escape(title)} | DINCR"><meta property="og:description" content="${escape(description)}">${image}<meta name="twitter:card" content="summary"><meta name="twitter:title" content="${escape(title)} | DINCR"><meta name="twitter:description" content="${escape(description)}"><link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="stylesheet" href="/style.css?v=${cssVersion}">${ld}</head><body>${LANGUAGES.map(lang => sites[lang].body(path)).join('')}</body></html>`;
}

const routes = Object.keys(sites.es.pages).filter(path => path !== '/404/');
await rm(out, { recursive: true, force: true }); await mkdir(out, { recursive: true });
for (const path of routes) { const dir = join(out, path); await mkdir(dir, { recursive: true }); await writeFile(join(dir, 'index.html'), layout(path)); }
// Cloudflare Pages treats a site without a root 404.html as an SPA. This is a static multipage site.
await writeFile(join(out, '404.html'), layout('/404/'));
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
if (base) await writeFile(join(out, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${routes.filter(x => !['/bancos-compatibles/'].includes(x) && (cfg.supportEmail || x != '/soporte/') && (cfg.googlePlayUrl || cfg.appStoreUrl || x != '/descargar/')).map(x => `<url><loc>${escape(url(x))}</loc></url>`).join('')}</urlset>`);
console.log(`Built ${routes.length} static public routes in ${out}`);
