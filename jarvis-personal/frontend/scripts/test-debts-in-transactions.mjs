// Debts shown inside Movimientos (Transactions) must be the Debts screen's own data,
// read-only, with nothing duplicated. Backend side (same endpoint, no writes,
// workspace isolation): backend/user_product/test_debts_in_transactions.py.
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (file) => fs.readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const api = read("src/users/services/jarvisApi.js");
const component = read("src/users/components/TransactionDebts.jsx");
const finance = read("src/users/pages/Finance.jsx");
const debtsPage = read("src/users/pages/Debts.jsx");
const registry = read("src/products/finva/features/registry.jsx");

// Same source: the one getDebts service, which is the Debts screen's endpoint.
assert.match(api, /export const getDebts = \(\) => request\("\/user-product\/finance\/debts"\);/);
assert.match(component, /import \{ getDebts \} from "\.\.\/services\/jarvisApi";/, "TransactionDebts reads through the shared service");
assert.match(debtsPage, /import \{[^}]*\bgetDebts\b[^}]*\} from "\.\.\/services\/jarvisApi";/, "the Debts screen reads through the same service");

// Read-only: no write service, no HTTP verb, no direct fetch, no local copy.
for (const forbidden of [/\bcreateDebt\b/, /\bupdateDebt\b/, /\bdeleteDebt\b/, /\bpayDebt\b/, /method:\s*"/, /\bfetch\(/, /localStorage|sessionStorage|indexedDB/]) {
  assert.doesNotMatch(component, forbidden, `TransactionDebts must stay read-only and keep no copy (${forbidden})`);
}
assert.equal((component.match(/getDebts\(/g) || []).length, 1, "one read per mount, no polling or recalculation");

// Integrated in Movimientos under the Debts filter; management stays in the Debts screen.
assert.match(finance, /import TransactionDebts from "\.\.\/components\/TransactionDebts";/);
assert.match(finance, /filter === "debt" && <TransactionDebts onManage=\{onNavigate \? \(\) => onNavigate\("debts"\) : undefined\}\/>/);
assert.match(finance, /\['debt',tx\('Deudas','Debts'\)\]/);

// Debts under Plan keeps working exactly as before.
assert.match(registry, /debts: <Debts plan=\{plan\} \/>/);
assert.match(read("src/products/finva/navigation/FinvaNavigation.jsx"), /activeKeys: \["plan", "debts"/);
for (const write of ["createDebt", "updateDebt", "deleteDebt", "payDebt"]) assert.match(debtsPage, new RegExp(`\\b${write}\\b`), `Debts screen still offers ${write}`);

console.log("Debts in Transactions: same source, read-only, no duplication, Debts screen intact.");
