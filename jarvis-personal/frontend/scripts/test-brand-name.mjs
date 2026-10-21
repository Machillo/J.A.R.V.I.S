// The product is DINCR. The legacy name (FINVA, any case) must never reach a person: no string a
// native app can show, no store copy, no landing page. test-i18n.mjs already guards the web app's
// copy with an AST walk; this covers the native apps (Kotlin, Swift, localized resources), the
// store texts and the built landing.
//
// Technical identifiers that keep the legacy name for compatibility (the mail OAuth return scheme
// and an API enum value) are allowed only as these exact literals. Anything else fails, so a new
// visible string with the old name cannot land. Comments are history, not copy, and are skipped.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const LEGACY = /finva/i;
// Exact technical literals, with the reason. See docs/brand/legacy-name-audit.md.
const ALLOWED_LITERALS = new Map([
  ["com.finva.app", "mail OAuth return scheme the backend still sends (FINVA_GMAIL_RETURN_URL); production config, human gate"],
  ["finva", "debt-plan method value of the VIP strategy API (`method`), never rendered"],
]);

const walk = (dir, accept) => {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return ["build", ".gradle", "node_modules", "DerivedData"].includes(entry.name) ? [] : walk(full, accept);
    return accept(full) ? [full] : [];
  });
};

/** Removes // and /* *\/ comments outside string literals (Kotlin, Swift). */
function stripComments(source) {
  let out = "";
  let i = 0;
  let quote = null;
  while (i < source.length) {
    const c = source[i];
    const next = source[i + 1];
    if (quote) {
      out += c;
      if (c === "\\") { out += next ?? ""; i += 2; continue; }
      if (source.startsWith(quote, i)) { out += quote.slice(1); i += quote.length; quote = null; continue; }
      i += 1;
      continue;
    }
    if (c === "/" && next === "/") { while (i < source.length && source[i] !== "\n") i += 1; continue; }
    if (c === "/" && next === "*") { const end = source.indexOf("*/", i + 2); i = end < 0 ? source.length : end + 2; continue; }
    if (source.startsWith('"""', i)) { quote = '"""'; out += quote; i += 3; continue; }
    if (c === '"') { quote = '"'; out += c; i += 1; continue; }
    out += c;
    i += 1;
  }
  return out;
}

const literals = (source) => [...stripComments(source).matchAll(/"""([\s\S]*?)"""|"((?:[^"\\\n]|\\.)*)"/g)].map((m) => m[1] ?? m[2]);
const rel = (file) => path.relative(repo, file).split(path.sep).join("/");

export function findLegacyNames(files) {
  const failures = [];
  for (const file of files) {
    const source = fs.readFileSync(file, "utf8");
    const code = /\.(kt|swift)$/.test(file);
    const values = code ? literals(source) : [source.replace(/<!--[\s\S]*?-->/g, "")];
    for (const value of values) {
      if (!LEGACY.test(value)) continue;
      if (code && ALLOWED_LITERALS.has(value)) continue;
      failures.push(`${rel(file)}: ${JSON.stringify(value.length > 120 ? `${value.slice(0, 120)}…` : value)}`);
    }
  }
  return failures;
}

const native = path.join(repo, "jarvis-personal/native");
const isTest = (file) => /[\\/](test|androidTest|DINCRUITests|Tests)[\\/]/.test(file) || /Tests?\.(kt|swift)$/.test(file);
const sources = [
  ...walk(path.join(native, "android"), (f) => /[\\/]src[\\/]main[\\/]/.test(f) && /\.(kt|xml)$/.test(f) && !isTest(f)),
  ...walk(path.join(native, "ios"), (f) => /\.(swift|strings|stringsdict|xcstrings)$/.test(f) && !isTest(f)),
  ...walk(path.join(repo, "jarvis-personal/store-assets/copy"), (f) => /\.json$/.test(f)),
  ...walk(path.join(repo, "jarvis-personal/frontend/landing"), (f) => /\.(mjs|json|css)$/.test(f)),
];
// XML in Android main holds manifests (with the transitional scheme) and resources: only
// resources are copy. Manifests are covered by test-android-identity.mjs.
const copyFiles = sources.filter((f) => !/AndroidManifest\.xml$/.test(f));
assert.ok(copyFiles.some((f) => f.endsWith(".kt")) && copyFiles.some((f) => f.endsWith(".swift")), "the native sources were found");

// The guard must catch what it exists for: a visible string and a resource with the old name.
{
  const dir = fs.mkdtempSync(path.join(fs.realpathSync(process.env.TMPDIR || process.env.TEMP || "/tmp"), "brand-"));
  const kt = path.join(dir, "Probe.kt");
  fs.writeFileSync(kt, 'val a = tx("Bienvenido a FINVA", "Welcome to Finva") // finva in a comment is fine\nval b = "com.finva.app"\n');
  const xml = path.join(dir, "strings.xml");
  fs.writeFileSync(xml, '<resources><!-- FINVA history --><string name="app_name">Finva</string></resources>');
  const found = findLegacyNames([kt, xml]);
  fs.rmSync(dir, { recursive: true, force: true });
  assert.equal(found.length, 3, `self-check: expected 3 findings, got ${found.join("; ")}`);
}

const failures = findLegacyNames(copyFiles);
assert.deepEqual(failures, [], `the legacy product name reaches users; the product is DINCR:\n  - ${failures.join("\n  - ")}`);
const built = path.join(repo, "jarvis-personal/frontend/landing-dist");
const builtFiles = walk(built, (f) => /\.(html|xml|txt|json)$/.test(f));
const builtFailures = builtFiles.flatMap((f) => (LEGACY.test(fs.readFileSync(f, "utf8")) ? [rel(f)] : []));
assert.deepEqual(builtFailures, [], `the built landing names the legacy product: ${builtFailures.join(", ")}`);
console.log(`brand name: ${copyFiles.length} native, store and landing files carry no legacy product name`
  + `${builtFiles.length ? `; built landing (${builtFiles.length} files) clean` : ""}`);
