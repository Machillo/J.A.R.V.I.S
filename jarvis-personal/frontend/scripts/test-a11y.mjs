// Static accessibility guard for the public DINCR (Users) surfaces: every icon-only
// button and every form control needs an accessible name, and clickable
// non-interactive elements need a role. Heuristic by design: it catches the
// regressions screen-reader users hit first; device testing (TalkBack/VoiceOver)
// remains manual.
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/", import.meta.url));
const surfaces = ["users", "products/finva", "components", "pages/Login.jsx", "pages/LegalConsent.jsx", "pages/FinvaOnboarding.jsx", "pages/ProfileSetup.jsx"];
const files = [];
const walk = (path) => statSync(path).isDirectory()
  ? readdirSync(path).forEach((name) => walk(join(path, name)))
  : path.endsWith(".jsx") && files.push(path);
surfaces.forEach((surface) => walk(join(root, surface)));

const TEXT_CALL = /\b(?:tx|copy|t|tr)\(|label|name|title|text|children|message|\?|&&/i;
const problems = [];
const where = (file, source, index) => `${file.slice(root.length).split("\\").join("/")}:${source.slice(0, index).split("\n").length}`;

for (const file of files) {
  const source = readFileSync(file, "utf8");
  for (const match of source.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
    const [, attrs, inner] = match;
    if (/aria-label=|aria-labelledby=|title=/.test(attrs)) continue;
    const visible = inner
      .replace(/<[^>]+\/>/g, "")
      .replace(/<[^>]+>/g, "")
      .replace(/\{[^}]*\}/g, (expression) => (TEXT_CALL.test(expression) ? "TEXT" : ""))
      .trim();
    if (!visible) problems.push(`icon-only button without a name: ${where(file, source, match.index)}`);
  }
  for (const match of source.matchAll(/<(input|select|textarea)\b([^>]*?)\/?>/g)) {
    const attrs = match[2];
    if (/type="hidden"|type="file"|aria-label=|aria-labelledby=|\bid=/.test(attrs)) continue;
    const before = source.slice(Math.max(0, match.index - 500), match.index);
    if (before.lastIndexOf("<label") > before.lastIndexOf("</label>")) continue;
    if (/Field\b[^>]*label=/.test(before.slice(before.lastIndexOf("<")))) continue;
    problems.push(`${match[1]} without a label: ${where(file, source, match.index)}`);
  }
  for (const match of source.matchAll(/<(div|span|li|article|p|strong|small)\b[^>]*?\bonClick=/g)) {
    const tag = source.slice(match.index, source.indexOf(">", match.index));
    if (/role=|tabIndex=|backdrop/.test(tag)) continue;
    problems.push(`clickable <${match[1]}> without a role: ${where(file, source, match.index)}`);
  }
  for (const match of source.matchAll(/<img\b([^>]*)>/g)) {
    if (!/alt=/.test(match[1])) problems.push(`img without alt: ${where(file, source, match.index)}`);
  }
}

assert.deepEqual(problems, [], `Accessibility regressions:\n${problems.join("\n")}`);
console.log(`DINCR Users accessibility guard passed (${files.length} screens and components).`);
