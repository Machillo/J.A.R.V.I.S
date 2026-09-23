// DINCR i18n contract: every visible string in the public app must follow the
// device language (Spanish or English) with no hardcoded single-language copy.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

const traverse = traverseModule.default;
const ENTRIES = ["src/App.jsx", "src/main.jsx"];
// DINCR Owner (JARVIS) and the legal documents are not part of the public
// bilingual UI: Owner is Spanish-only by design and the legal texts are the
// Spanish documents accepted at sign-up.
const OUT_OF_SCOPE = [/src[\\/]personal[\\/]/, /src[\\/]products[\\/]jarvis[\\/]/, /PublicInfoPage\.jsx$/];

// Small, explicit allowlist. Each entry names the file, the exact text and why
// it is not localized.
const ALLOWLIST = [
  // Canonical Spanish category values stored by the backend; the UI shows them through categoryLabel().
  { file: "src/users/pages/Finance.jsx", pattern: /^(Boleta de pago|Bono|Reembolso|Otros ingresos|Vivienda|Servicios|Internet|Teléfono|Seguros|Comida|Restaurante|Transporte|Gasolina|Entretenimiento|Compras|Salud|Deporte|Servicios personales|Mascotas|Otros)$/, reason: "canonical category value" },
  // English presentation maps for Spanish backend copy.
  { file: "src/lib/planCopy.js", pattern: /.*/, reason: "English translation of backend plan copy" },
  { file: "src/lib/categories.js", pattern: /.*/, reason: "English labels for canonical categories" },
  { file: "src/products/finva/features/vip/VipScreens.jsx", pattern: /^(Without positive cash flow|It protects your|It is the lowest-cost|It aligns the contribution|Cash flow, reserves|Pay extra toward|Fund )/, reason: "English translation map for backend strategy copy" },
  // Stored note sent to a legacy endpoint (data, not UI).
  { file: "src/services/jarvisApi.js", pattern: /^Cuenta manual \(/, reason: "stored record note, not visible copy" },
  // Owner-only endpoints (legacy finance input and owner billing receipts).
  { file: "src/services/jarvisApi.js", pattern: /^(No pude leer el PDF\.|No se pudo abrir el comprobante)/, reason: "DINCR Owner-only endpoint" },
  // Bank proper names.
  { file: "src/pages/ProfileSetup.jsx", pattern: /^(Banco de Costa Rica|Banco Nacional|Banco Popular)$/, reason: "bank name" },
  // Diagnostics never shown to users.
  { file: "src/lib/telemetry.js", pattern: /^(Unhandled JavaScript error|Unhandled promise rejection|Unknown error)$/, reason: "crash-report diagnostic" },
  { file: "src/lib/featureFlags.js", pattern: /request failed/, reason: "developer diagnostic" },
  { file: "src/lib/releasePolicy.js", pattern: /request failed/, reason: "developer diagnostic" },
  // Owner web-push helper (JARVIS PWA only).
  { file: "src/pushNotifications.js", pattern: /.*/, reason: "DINCR Owner-only web push" },
];

// Brands, feature names (DINCR Today), plan names, currencies, codes and words
// spelled the same in both languages (Plan, Balance).
const NEUTRAL_TEXT = /^(?:DINCR(?: · (?:FREE|BASIC|VIP))?|DINCR ·|DINCR Today|Plan|Balance|VIP ·|VIP|Basic|Free|Gmail|Outlook|Outlook \/ Hotmail ·|Google|Apple|Face ID|Touch ID|Passkey \/ Face ID|BAC|SINPE|MultiMoney|IBKR|CCSS|CRC|USD|Internet|Total|Email|OK|iris|Premium|Personal|General|[\d\s.,:+/–—→−%$₡#()·•-]+)$/i;
const SPANISH = /[áéíóúñ¿¡]|\b(de|del|la|las|los|el|tu|tus|una|con|para|por|sin|que|pudimos|pude|podés|revisá|intentá|agregar|guardar|cuenta|correo|movimiento|pago|gasto|ingreso|deuda|meta|ahorro|cerrar|volver|nuevo|nueva|hoy|mes|meses|año|elegí|salir|reintentar|cargando|preparando|continuar|omitir)\b/i;
const ENGLISH = /\b(the|your|you|and|with|without|for|to|of|is|are|add|save|close|back|try|again|couldn[’']?t|payment|account|transaction|expense|income|debt|goal|savings|new|today|month|year|please|loading|error|choose|skip|continue|retry)\b/i;
const HUMAN = /\p{L}{2,}.*\s.*\p{L}{2,}|[áéíóúñ¿¡]/u;
const TECHNICAL = /^(?:[a-z0-9_\-.:/@#?=&%{}]+|[A-Z0-9_]+|https?:\/\/\S+|\S+\.(?:css|svg|png|js|jsx))$/;
const VISIBLE_ATTRS = new Set(["aria-label", "placeholder", "title", "alt", "label", "caption", "eyebrow", "summary", "subtitle", "description", "message", "confirmLabel", "cancelLabel"]);
const COPY_CALLS = new Set(["tx", "t", "tr", "copy"]);
const NON_UI_CALLS = new Set(["addEventListener", "removeEventListener", "dispatchEvent", "CustomEvent", "getItem", "setItem", "removeItem", "querySelector", "trackEvent", "captureProductEvent", "recordError", "startsWith", "includes", "replace", "replaceAll", "split", "match", "test", "log", "warn", "debug", "info", "join", "DOMException", "fetch", "request", "jsonRequest", "open", "matchMedia", "RegExp", "URL", "URLSearchParams"]);
const NON_UI_ATTRS = /^(className|key|id|type|name|role|href|src|htmlFor|inputMode|autoComplete|rel|target|method|accept|d|viewBox|fill|stroke|value|to|provider|variant|tone|kind|screen|surface|list|defaultValue|pattern|lang|min|max|step)$/;

const toPosix = (file) => path.relative(process.cwd(), file).split(path.sep).join("/");
const calleeName = (callee) => callee?.type === "Identifier" ? callee.name : callee?.type === "MemberExpression" ? callee.property?.name : null;
const flatten = (value) => String(value).replace(/\s+/g, " ").trim();

function resolveImport(from, spec) {
  if (!spec.startsWith(".")) return null;
  const base = path.resolve(path.dirname(from), spec);
  return [base, `${base}.js`, `${base}.jsx`, path.join(base, "index.js"), path.join(base, "index.jsx")]
    .find((candidate) => fs.existsSync(candidate) && fs.statSync(candidate).isFile() && /\.(jsx?|mjs)$/.test(candidate)) || null;
}

function publicFiles() {
  const files = new Set();
  const queue = ENTRIES.map((entry) => path.resolve(entry));
  while (queue.length) {
    const file = queue.pop();
    if (files.has(file) || OUT_OF_SCOPE.some((pattern) => pattern.test(file))) continue;
    files.add(file);
    const source = fs.readFileSync(file, "utf8");
    for (const match of source.matchAll(/(?:import|export)\s[^'"]*?from\s+["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)/g)) {
      const resolved = resolveImport(file, match[1] || match[2]);
      if (resolved) queue.push(resolved);
    }
  }
  return [...files].sort();
}

const parseFile = (file) => parse(fs.readFileSync(file, "utf8"), { sourceType: "module", plugins: ["jsx"] });

// ---- 1. Dictionary parity -------------------------------------------------
function dictionaryKeys() {
  const ast = parseFile(path.resolve("src/lib/locale.js"));
  let dictionaries = null;
  traverse(ast, {
    VariableDeclarator(p) {
      if (p.node.id.name === "dictionaries") dictionaries = p.node.init;
    },
  });
  assert.ok(dictionaries, "locale.js must declare the dictionaries object");
  const collect = (node, prefix = "") => node.properties.flatMap((property) => {
    const key = `${prefix}${property.key.name ?? property.key.value}`;
    if (property.value.type === "ObjectExpression") return collect(property.value, `${key}.`);
    assert.equal(property.value.type, "StringLiteral", `${key} must be a plain string`);
    assert.ok(property.value.value.trim(), `${key} must not be empty`);
    return [key];
  });
  const byLanguage = Object.fromEntries(dictionaries.properties.map((property) => [property.key.name, new Set(collect(property.value))]));
  return byLanguage;
}

const keys = dictionaryKeys();
assert.deepEqual(Object.keys(keys).sort(), ["en", "es"], "locale.js must define exactly es and en");
const missingInEnglish = [...keys.es].filter((key) => !keys.en.has(key));
const missingInSpanish = [...keys.en].filter((key) => !keys.es.has(key));
assert.deepEqual(missingInEnglish, [], `keys missing in en: ${missingInEnglish.join(", ")}`);
assert.deepEqual(missingInSpanish, [], `keys missing in es: ${missingInSpanish.join(", ")}`);

// ---- 2. Public UI scan ----------------------------------------------------
const files = publicFiles();
const issues = [];
const usedKeys = new Set();
const allowed = (file, value) => ALLOWLIST.some((entry) => entry.file === file && entry.pattern.test(value));
const report = (file, node, kind, value) => {
  const text = flatten(value);
  if (!allowed(file, text)) issues.push(`${file}:${node.loc?.start.line || 0} [${kind}] ${text.slice(0, 100)}`);
};
const literalText = (node) => node?.type === "StringLiteral" ? node.value
  : node?.type === "TemplateLiteral" ? node.quasis.map((quasi) => quasi.value.cooked).join("{}") : null;

function isBilingualStructure(p) {
  const parent = p.parentPath;
  // ["español", "English"] pairs.
  if (parent?.isArrayExpression() && parent.node.elements.length === 2) return true;
  // { message_es: "…", message_en: "…" }.
  if (parent?.isObjectProperty() && /_(es|en)$/.test(parent.node.key.name || parent.node.key.value || "")) return true;
  // language === "es" ? "…" : "…".
  if (parent?.isConditionalExpression()) {
    const test = parent.node.test;
    if (test.type === "BinaryExpression" && [test.left, test.right].some((side) => side.type === "StringLiteral" && ["es", "en"].includes(side.value))) return true;
  }
  return false;
}

for (const file of files) {
  const relative = toPosix(file);
  if (relative === "src/lib/locale.js") continue; // checked by the parity contract above
  traverse(parseFile(file), {
    JSXText(p) {
      const text = flatten(p.node.value);
      if (text.length > 1 && /\p{L}/u.test(text) && !NEUTRAL_TEXT.test(text)) report(relative, p.node, "jsx-text", text);
    },
    JSXAttribute(p) {
      const value = p.node.value;
      if (VISIBLE_ATTRS.has(p.node.name?.name) && value?.type === "StringLiteral" && /\p{L}{2}/u.test(value.value) && !NEUTRAL_TEXT.test(value.value)) {
        report(relative, value, `attr:${p.node.name.name}`, value.value);
      }
    },
    CallExpression(p) {
      const name = calleeName(p.node.callee);
      if ((name === "t" || name === "tr") && p.node.arguments[0]?.type === "StringLiteral" && /^[a-z]+\.[A-Za-z]+$/.test(p.node.arguments[0].value)) {
        usedKeys.add(p.node.arguments[0].value);
      }
      if (name !== "tx" && name !== "copy") return;
      const [spanish, english] = p.node.arguments.slice(0, 2).map(literalText);
      if (spanish == null || english == null) return;
      if (spanish === english && /\p{L}{3}/u.test(spanish) && !NEUTRAL_TEXT.test(spanish)) report(relative, p.node, "same-es-en", spanish);
      else if (/[áéíóúñ¿¡]/.test(english.replace(/colón/g, ""))) report(relative, p.node, "english-has-spanish", english);
    },
    "StringLiteral|TemplateLiteral"(p) {
      const value = literalText(p.node);
      if (!value || !HUMAN.test(value) || TECHNICAL.test(value.trim()) || NEUTRAL_TEXT.test(value.trim())) return;
      const parent = p.parentPath;
      if (parent.isImportDeclaration() || parent.isExportNamedDeclaration() || parent.isJSXAttribute()) return;
      if (parent.isObjectProperty() && parent.node.key === p.node) return;
      if (parent.isBinaryExpression() && ["===", "!==", "==", "!="].includes(parent.node.operator)) return;
      if ((parent.isCallExpression() || parent.isNewExpression()) && NON_UI_CALLS.has(calleeName(parent.node.callee))) return;
      if (p.findParent((q) => q.isCallExpression() && COPY_CALLS.has(calleeName(q.node.callee)))) return;
      if (p.findParent((q) => q.isJSXAttribute() && NON_UI_ATTRS.test(q.node.name?.name || ""))) return;
      if (isBilingualStructure(p)) return;
      if (SPANISH.test(value)) report(relative, p.node, "spanish-only", value);
      else if (ENGLISH.test(value)) report(relative, p.node, "english-only", value);
    },
  });
}

const unknownKeys = [...usedKeys].filter((key) => !keys.es.has(key) || !keys.en.has(key));
assert.deepEqual(unknownKeys, [], `t() keys missing from the catalogs: ${unknownKeys.join(", ")}`);

// ---- 3. Critical first-run screens ---------------------------------------
for (const critical of ["src/pages/Login.jsx", "src/pages/LegalConsent.jsx", "src/pages/ProfileSetup.jsx", "src/pages/FinvaOnboarding.jsx", "src/pages/FinvaWelcomeStory.jsx", "src/users/pages/Settings.jsx"]) {
  assert.ok(files.some((file) => toPosix(file) === critical), `${critical} must be part of the scanned public UI`);
}
const onboarding = fs.readFileSync("src/pages/FinvaOnboarding.jsx", "utf8");
assert.match(onboarding, /tx\("Elegí tu plan personal", "Choose your personal plan"\)/);
assert.doesNotMatch(onboarding, /toLocaleString\("es-CR"\)/, "onboarding prices must follow the device locale");
const welcome = fs.readFileSync("src/pages/FinvaWelcomeStory.jsx", "utf8");
assert.match(welcome, /tx\("Omitir", "Skip"\)/);
assert.match(welcome, /tx\("Continuar", "Continue"\)/);

if (issues.length) {
  console.error(issues.join("\n"));
  console.error(`\n${issues.length} hardcoded single-language string(s) in the public DINCR UI.`);
  process.exit(1);
}

console.log(`i18n contract passed: ${keys.es.size} catalog keys in es/en, ${usedKeys.size} used keys, ${files.length} public files scanned.`);
