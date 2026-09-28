// Bank branding resolver + Accounts screens (Owner and DINCR Users VIP).
import assert from "node:assert/strict";
import fs from "node:fs";
import { BANK_IDENTITIES, describeBank, identifyBank, identifyBankInText } from "../src/lib/bankIdentity.js";

const read = (path) => fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const id = (value) => identifyBank(value)?.id ?? null;

// Codes, names, alternative spellings and accents resolve to one bank.
assert.equal(id("bac"), "bac");
assert.equal(id("BAC Credomatic"), "bac");
assert.equal(id("multimoney"), "multimoney");
assert.equal(id("Multi Money"), "multimoney");
assert.equal(id("MM"), "multimoney");
assert.equal(id("popular"), "popular");
assert.equal(id("Banco Popular y de Desarrollo Comunal"), "popular");
assert.equal(id("BCR"), "bcr");
assert.equal(id("Banco de Costa Rica"), "bcr");
assert.equal(id("Banco Nacional de Costa Rica"), "bn", "Banco Nacional is not Banco de Costa Rica");
assert.equal(id("BANCO NACIONAL"), "bn");
assert.equal(id("Davivienda"), "davivienda");
assert.equal(id("Davibank"), "davibank");
assert.equal(id("Promérica"), "promerica");
assert.equal(id("unknown"), null);
assert.equal(id(""), null);
assert.equal(id(null), null);
// Short codes only match exactly, never inside other words.
assert.equal(identifyBankInText("Notificación de transacción BAC Credomatic <alertas@baccredomatic.com>")?.id, "bac");
assert.equal(identifyBankInText("Su comprobante bncr.fi.cr")?.id, "bn");
assert.equal(identifyBankInText("Cabinas del bosque"), null);
assert.equal(identifyBankInText("Compra en BPM Store"), null);

// Unknown institutions keep a safe initials fallback.
assert.deepEqual(describeBank("coopealianza", "Coopealianza"), { id: "coopealianza", name: "Coopealianza", short: "COO" });
assert.equal(describeBank("", "Mutual Cartago de Ahorro").short, "MC");
assert.equal(describeBank("", "").short, "?");

// Every known bank has its logo asset on disk.
const branding = read("src/lib/bankBranding.js");
for (const bank of BANK_IDENTITIES) {
  const logo = branding.match(new RegExp(`\\b${bank.id}: (\\w+)`))?.[1];
  assert.ok(logo, `${bank.id} has a logo`);
  const asset = branding.match(new RegExp(`import ${logo} from "\\.\\./assets/institutions/([^"]+)"`))?.[1];
  assert.ok(asset && fs.existsSync(new URL(`../src/assets/institutions/${asset}`, import.meta.url)), `${bank.id} logo file exists`);
}
assert.match(read("src/components/BankLogo.jsx"), /onError=\{\(\) => setFailed\(true\)\}/, "a broken image falls back to initials");

// Owner Accounts: real logos through the central resolver, no hardcoded initials.
const owner = read("src/pages/FinancialAccounts.jsx");
assert.match(owner, /import \{ BANKS, findBankInText, resolveBank \} from "\.\.\/lib\/bankBranding";/);
assert.match(owner, /<BankLogo bank=\{bank\}\/>/);
assert.doesNotMatch(owner, /short: "MM"|\{bank\.short\}<\/span>/);

// DINCR Users Accounts: VIP only (same gate as bank emails), same review flow and
// endpoints as the mail screen, no Owner services or screens.
const registry = read("src/products/finva/features/registry.jsx");
assert.match(registry, /accounts: plan === "vip" \? gated\("gmail_automation", <GmailAutomation view="accounts" onNavigate=\{navigate\} \/>\)/);
const users = read("src/users/pages/GmailAutomation.jsx");
assert.match(users, /from "\.\.\/services\/jarvisApi";/);
assert.doesNotMatch(users, /\.\.\/\.\.\/services\/jarvisApi|pages\/FinancialAccounts|personal\/|products\/jarvis/, "no Owner code in Users");
assert.equal((users.match(/acceptVipGmailCandidate\(/g) || []).length, 1, "one accept path");
assert.equal((users.match(/rejectVipGmailCandidate\(/g) || []).length, 1, "one reject path");
assert.match(users, /getVipGmailEmails\(accountsView \? "" : filter\)/);
// The list endpoint returns the newest 200 messages: pending items are loaded too.
assert.match(users, /accountsView \? getVipGmailEmails\("pending"\) : null/);
assert.match(users, /if \(bankId && !institutions\.some\(\(entry\) => entry\.bank\.id === bankId\)\) setBankId\(null\);/);
assert.match(users, /accountsView && gmail\?\.needs_reauthorization/);
// Amounts keep their own currency (CRC and USD are never mixed).
assert.match(users, /currency: String\(currency \|\| ""\)\.toUpperCase\(\) === "USD" \? "USD" : "CRC"/);
// A USD movement shows its USD amount, not the parser's converted colones (test-mail-currency.mjs).
assert.match(users, /<b>\{money\(nativeMoney\(item\)\.amount, nativeMoney\(item\)\.currency\)\}<\/b>/);
assert.match(read("src/products/finva/features/hubs/FinvaHubs.jsx"), /if \(plan === "vip"\) account\.splice\(1, 0,\s*item\(navigate, "accounts",/);

console.log("Bank accounts checks passed.");
