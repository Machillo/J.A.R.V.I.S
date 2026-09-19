import fs from "node:fs";
import path from "node:path";
import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

const traverse = traverseModule.default;
const scopeIndex = process.argv.indexOf("--scope");
const requestedScope = scopeIndex >= 0 ? process.argv[scopeIndex + 1] : "src";
if (!requestedScope || requestedScope.startsWith("-") || path.isAbsolute(requestedScope) || requestedScope.split(/[\\/]+/).includes("..")) {
  throw new Error("--scope must be a relative directory inside this project");
}
const root = path.resolve(requestedScope);
if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
  throw new Error(`Audit scope does not exist: ${requestedScope}`);
}
const extensions = new Set([".js", ".jsx"]);
const visibleAttributes = new Set(["aria-label", "placeholder", "title", "alt"]);
const safeText = /^(?:(?:FINVA|J\.?A\.?R\.?V\.?I\.?S\.?|VIP|BASIC|FREE)(?:\s+(?:VIP|BASIC|FREE|\d+))?|Google|Apple|Face ID|Passkey|Passkey\s*\/\s*Face ID|Gmail|SINPE|BAC|MultiMoney|IBKR|CRC|USD|OpenAI|Gemini|Supabase|Render|Vercel|Firebase|ChatGPT|[\d\s.,:+/–—→−%$₡#()]+)$/i;
const issues = [];

function filesAt(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    return entry.isDirectory() ? filesAt(full) : extensions.has(path.extname(entry.name)) ? [full] : [];
  });
}

function normalized(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function isVisibleCopy(value) {
  const text = normalized(value);
  return text.length > 1 && /\p{L}/u.test(text) && !safeText.test(text);
}

function add(file, node, kind, value) {
  issues.push({ file: path.relative(process.cwd(), file), line: node.loc?.start.line || 1, kind, value: normalized(value) });
}

for (const file of filesAt(root)) {
  const source = fs.readFileSync(file, "utf8");
  const ast = parse(source, { sourceType: "module", plugins: ["jsx"] });
  traverse(ast, {
    JSXText(p) {
      if (isVisibleCopy(p.node.value)) add(file, p.node, "visible JSX text", p.node.value);
    },
    JSXAttribute(p) {
      const name = p.node.name?.name;
      const value = p.node.value;
      if (visibleAttributes.has(name) && value?.type === "StringLiteral" && isVisibleCopy(value.value)) {
        add(file, value, `hardcoded ${name}`, value.value);
      }
    },
    StringLiteral(p) {
      if (p.node.value !== "es-CR") return;
      const parent = p.parentPath;
      if (parent.isCallExpression() || parent.isNewExpression()) add(file, p.node, "fixed locale", p.node.value);
    },
  });
}

if (issues.length) {
  for (const issue of issues) console.error(`${issue.file}:${issue.line} [${issue.kind}] ${issue.value}`);
  console.error(`\n${issues.length} localization issue(s) found.`);
  process.exit(1);
}

console.log("UI language audit passed.");
