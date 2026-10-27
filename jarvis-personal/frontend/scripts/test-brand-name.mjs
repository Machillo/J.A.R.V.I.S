// The product is DINCR. The legacy name (FINVA, in any case) must never reach a person: no string
// a native app can show, no app name, manifest, Info.plist or build setting, no store copy, no
// landing page. test-i18n.mjs guards the web app's copy with an AST walk (FINVA / Finva); this
// covers the native apps (Kotlin, Swift, localized resources, manifests, Info.plist, xcconfig,
// Gradle), the Capacitor shells' resources and manifests, the store texts and the built landing.
//
// Technical identifiers that keep the legacy name for compatibility (the mail OAuth return scheme
// and an API enum value) are allowed only as exact tokens, and only in the files listed below.
// Anything else fails, so a new visible string with the old name cannot land. Comments are
// history, not copy, and are skipped. See jarvis-personal/docs/brand/legacy-name-audit.md.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const LEGACY = /finva/i;
const SCHEME = "mail OAuth return scheme the backend still sends (FINVA_GMAIL_RETURN_URL); production config, human gate (audit C7)";
const METHOD = "debt-plan method value of the VIP strategy API, in the fixture backends; never rendered (audit C9)";
const STORE = "store product id the backend's catalog defaults to, mirrored by the fixture backend; the stores show the product's title, never its id (audit C8)";
/** file (repo-relative) → token → reason. A token is the exact string literal (code) or word (config). */
export const ALLOWED = {
  "jarvis-personal/native/android/app/src/main/kotlin/com/dincr/app/AppModel.kt": { "com.finva.app": SCHEME },
  "jarvis-personal/native/android/app/build.gradle.kts": { "com.finva.app": SCHEME },
  "jarvis-personal/native/android/core/data/src/main/kotlin/com/dincr/data/FakeBackend.kt": { finva: METHOD },
  "jarvis-personal/native/ios/Config/Info.plist": { "com.finva.app": SCHEME },
  "jarvis-personal/native/ios/DINCR/App/AppModel.swift": { "com.finva.app": SCHEME },
  "jarvis-personal/native/ios/DincrKit/Sources/DincrCore/FixtureBackend.swift": {
    finva: METHOD, "com.finva.app": SCHEME, "finva.\\($0).monthly": STORE, "finva.\\($0).annual": STORE,
  },
  "jarvis-personal/frontend/android/app/src/main/AndroidManifest.xml": { "com.finva.app": SCHEME },
  "jarvis-personal/frontend/ios-dincr/App/App/Info.plist": { "com.finva.app": SCHEME },
};

const walk = (dir, accept) => {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return ["build", ".gradle", "node_modules", "DerivedData", "Pods"].includes(entry.name) ? [] : walk(full, accept);
    return accept(full) ? [full] : [];
  });
};

/** Removes // and /* *\/ comments outside string and char literals (Kotlin, Swift, Gradle). */
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
    // A Kotlin char literal ('"', '\'') must not open a string.
    const char = /^'(?:\\.|[^'\\])'/.exec(source.slice(i, i + 4));
    if (char) { out += char[0]; i += char[0].length; continue; }
    if (source.startsWith('"""', i)) { quote = '"""'; out += quote; i += 3; continue; }
    if (c === '"') { quote = '"'; out += c; i += 1; continue; }
    out += c;
    i += 1;
  }
  return out;
}

const rel = (file) => path.relative(repo, file).split(path.sep).join("/");
const codeLiterals = (source) => [...stripComments(source).matchAll(/"""([\s\S]*?)"""|"((?:[^"\\\n]|\\.)*)"/g)].map((m) => m[1] ?? m[2]);
const configWords = (source, file) => {
  const text = /\.(xml|plist|strings|stringsdict|xcstrings)$/.test(file) ? source.replace(/<!--[\s\S]*?-->/g, "")
    : /\.xcconfig$/.test(file) ? source.replace(/^\s*\/\/.*$/gm, "")
      : source;
  return [...text.matchAll(/[\w.:/@-]*finva[\w.:/@-]*/gi)].map((m) => m[0]);
};

export function findLegacyNames(files, allowed = ALLOWED) {
  const failures = [];
  for (const file of files) {
    const source = fs.readFileSync(file, "utf8");
    const own = allowed[rel(file)] ?? {};
    const code = /\.(kt|kts|swift)$/.test(file);
    const values = code ? codeLiterals(source) : configWords(source, file);
    for (const value of values) {
      if (!LEGACY.test(value)) continue;
      const token = code ? value : value.replace(/:\/\/.*$/, "").replace(/[.:/]+$/, "");
      if (Object.hasOwn(own, token)) continue;
      failures.push(`${rel(file)}: ${JSON.stringify(value.length > 120 ? `${value.slice(0, 120)}…` : value)}`);
    }
  }
  return failures;
}

const native = path.join(repo, "jarvis-personal/native");
const capacitor = path.join(repo, "jarvis-personal/frontend");
const isTest = (file) => /[\\/](test|androidTest|DINCRUITests|DincrKitTests|Tests)[\\/]/.test(file) || /Tests?\.(kt|swift)$/.test(file);
const CONFIG = /\.(xml|plist|strings|stringsdict|xcstrings|xcconfig|kts)$/;
const files = [
  // Native Android: app and core sources, resources, manifests, Gradle (app name, resValue, placeholders).
  ...walk(path.join(native, "android"), (f) => !isTest(f) && (/[\\/]src[\\/]main[\\/]/.test(f) ? /\.(kt|xml)$/.test(f) : /\.kts$/.test(f))),
  // Native iOS: Swift, localized resources, Info.plist (Face ID text), xcconfig (display name).
  ...walk(path.join(native, "ios"), (f) => !isTest(f) && /\.(swift|strings|stringsdict|xcstrings|plist|xcconfig)$/.test(f)),
  // Capacitor shells: Android resources and manifest, iOS Info.plist and strings.
  ...walk(path.join(capacitor, "android/app/src/main"), (f) => /\.xml$/.test(f)),
  ...walk(path.join(capacitor, "ios-dincr/App/App"), (f) => CONFIG.test(f)),
  // Store copy and the landing sources.
  ...walk(path.join(repo, "jarvis-personal/store-assets/copy"), (f) => /\.json$/.test(f)),
  ...walk(path.join(capacitor, "landing"), (f) => /\.(mjs|json|css)$/.test(f)),
];
for (const required of ["AndroidManifest.xml", "Info.plist", "Base.xcconfig", "build.gradle.kts", "strings.xml"]) {
  assert.ok(files.some((f) => path.basename(f) === required), `the guard scans ${required}`);
}
assert.ok(files.some((f) => f.endsWith(".kt")) && files.some((f) => f.endsWith(".swift")), "the native sources were found");
for (const file of Object.keys(ALLOWED)) assert.ok(fs.existsSync(path.join(repo, file)), `allow-listed file exists: ${file}`);

// The guard must catch what it exists for, and an allowed token outside its file must fail.
{
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "brand-"));
  const kt = path.join(dir, "Probe.kt");
  fs.writeFileSync(kt, "val q = '\"'\nval a = tx(\"Bienvenido a FINVA\", \"Welcome to Finva\") // finva in a comment is fine\nval b = \"com.finva.app\"\nval c = Text(\"finva\")\n");
  const xml = path.join(dir, "AndroidManifest.xml");
  fs.writeFileSync(xml, '<manifest><!-- FINVA history --><application android:label="Finva" /></manifest>');
  const plist = path.join(dir, "Info.plist");
  fs.writeFileSync(plist, "<plist><key>NSFaceIDUsageDescription</key><string>FinVA usa Face ID</string></plist>");
  const found = findLegacyNames([kt, xml, plist]);
  fs.rmSync(dir, { recursive: true, force: true });
  assert.equal(found.length, 6, `self-check: expected 6 findings, got ${found.length}: ${found.join("; ")}`);
}

const failures = findLegacyNames(files);
assert.deepEqual(failures, [], `the legacy product name reaches users; the product is DINCR:\n  - ${failures.join("\n  - ")}`);
const built = path.join(capacitor, "landing-dist");
const builtFiles = walk(built, (f) => /\.(html|xml|txt|json)$/.test(f));
const builtFailures = builtFiles.flatMap((f) => (LEGACY.test(fs.readFileSync(f, "utf8")) ? [rel(f)] : []));
assert.deepEqual(builtFailures, [], `the built landing names the legacy product: ${builtFailures.join(", ")}`);
console.log(`brand name: ${files.length} native, Capacitor shell, store and landing files carry no legacy product name`
  + `${builtFiles.length ? `; built landing (${builtFiles.length} files) clean` : ""}`);
