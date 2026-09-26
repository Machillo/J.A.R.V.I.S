import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import {
  baseCurrency, entryCurrencies, entryCurrencyPayload, entryFormAmount, formatMoney,
  latestUserRate, setBaseCurrency, toBaseAmount,
} from "../src/lib/currency.js";

// An older backend declares no entry currencies: it would ignore `currency` and
// `exchange_rate` and store a USD figure as base. Only the base is offered, and a
// stored foreign entry is edited by its base amount (the older-app behavior).
setBaseCurrency("CRC");
assert.deepEqual(entryCurrencies(), ["CRC"], "no declaration, no other currency");
assert.deepEqual(entryFormAmount({ amount: 50500, original_amount: 100, original_currency: "USD", exchange_rate: 505 }),
  { amount: 50500, currency: "CRC", exchange_rate: "" }, "never the typed USD figure read as colones");
setBaseCurrency("USD", ["USD"]);
assert.deepEqual(entryCurrencies(), ["USD"]);

// CRC account (the default), on a backend that declares CRC and USD.
setBaseCurrency("CRC", ["CRC", "USD"]);
assert.equal(baseCurrency(), "CRC");
assert.deepEqual(entryCurrencies(), ["CRC", "USD"]);
assert.equal(toBaseAmount(100, "USD", 505), 50500, "USD uses the user's rate");
assert.equal(toBaseAmount(100, "USD", ""), null, "no rate, no guess");
assert.equal(toBaseAmount(15000, "CRC", ""), 15000);
assert.deepEqual(entryCurrencyPayload({ currency: "USD", exchange_rate: "505" }), { currency: "USD", exchange_rate: 505 });
assert.deepEqual(entryCurrencyPayload({ currency: "CRC", exchange_rate: "505" }), { currency: null, exchange_rate: null },
  "a base entry clears any previous foreign amount");
assert.match(formatMoney(1500), /₡/);
assert.match(formatMoney(12.5, "USD"), /\$12[.,]50/);

// Editing shows what the user typed, in its currency; base rows stay as stored.
assert.deepEqual(entryFormAmount({ amount: 50500, original_amount: 100, original_currency: "USD", exchange_rate: 505 }),
  { amount: 100, currency: "USD", exchange_rate: 505 });
assert.deepEqual(entryFormAmount({ amount: 15000 }), { amount: 15000, currency: "CRC", exchange_rate: "" });
assert.equal(latestUserRate([
  { transaction_date: "2026-09-01", exchange_rate: 500 },
  { transaction_date: "2026-09-20", exchange_rate: 507.5 },
  { transaction_date: "2026-09-25" },
]), "507.5", "the user's own latest rate prefills the next entry");
assert.equal(latestUserRate([]), "");
assert.equal(latestUserRate([{ origin: "transaction", transaction_date: "2026-09-30", exchange_rate: 495 },
  { origin: "expense", transaction_date: "2026-09-01", exchange_rate: 510 }]), "510", "a parser's rate is never the prefill");

// USD account: formatting and conversion follow the base, not a hardcoded ₡.
setBaseCurrency("USD", ["CRC", "USD"]);
assert.deepEqual(entryCurrencies(), ["CRC", "USD"]);
assert.match(formatMoney(12), /\$/);
assert.doesNotMatch(formatMoney(12), /₡/);
assert.equal(toBaseAmount(50500, "CRC", 505), 100);
assert.deepEqual(entryFormAmount({ amount: 20 }), { amount: 20, currency: "USD", exchange_rate: "" });

// Legacy base currency: only its own currency is offered, and it is sent as null.
setBaseCurrency("EUR", ["EUR"]);
assert.deepEqual(entryCurrencies(), ["EUR"]);
setBaseCurrency("EUR", ["CRC", "USD"]);
assert.deepEqual(entryCurrencies(), ["EUR"], "a legacy base never gets a conversion it cannot do");
assert.deepEqual(entryCurrencyPayload({ currency: "EUR" }), { currency: null, exchange_rate: null });
setBaseCurrency("CRC", ["CRC", "USD"]);

// Income, expense and history edits send the currency on every create and edit.
const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");
const finance = source("users/pages/Finance.jsx");
assert.match(finance, /entryPayload = \(form\) => \(\{[^}]*\.\.\.entryCurrencyPayload\(form\)/);
assert.match(finance, /createIncome\(entryPayload\(incomeForm\)\)/);
assert.match(finance, /createExpense\(entryPayload\(expenseForm\)\)/);
assert.match(finance, /const payload=entryPayload\(editing\)/);
assert.match(finance, /\.\.\.entryFormAmount\(item\)/, "editing starts from the typed amount and currency");
const history = source("users/pages/Transactions.jsx");
assert.match(history, /manualEntry\(edit\) \? entryCurrencyPayload\(edit\)/);
for (const [name, text] of [["Finance", finance], ["Transactions", history]]) {
  assert.doesNotMatch(text, /currency:\s*"CRC"/, `${name} does not hardcode CRC formatting`);
  assert.doesNotMatch(text, /<b>₡<\/b>/, `${name} does not hardcode the ₡ symbol`);
}
assert.match(source("users/UsersApp.jsx"), /setBaseCurrency\(user\?\.base_currency, user\?\.entry_currencies\)/);

// No Users screen hardcodes colones: a USD account must not see ₡ on its own money.
// (GmailAutomation formats each bank movement in its own currency; Settings shows store prices.)
const walk = (dir) => readdirSync(new URL(`../src/${dir}`, import.meta.url)).flatMap((name) => {
  const path = `${dir}/${name}`;
  return statSync(new URL(`../src/${path}`, import.meta.url)).isDirectory() ? walk(path) : [path];
});
// PremiumStrategy is the VIP Users strategy screen (shared with the Owner, which stays CRC).
const premium = source("pages/PremiumStrategy.jsx");
assert.match(premium, /baseCurrency\(\) === "CRC" \? `₡\$\{Math\.round/);
assert.doesNotMatch(premium, /<span>₡<\/span>/);
// CCSS payroll orders are always in colones: the aguinaldo is never shown in a USD base.
const vip = source("products/finva/features/vip/VipScreens.jsx");
const aguinaldo = vip.slice(vip.indexOf("function VipAguinaldo"), vip.indexOf("function VipPreferences"));
assert.match(vip, /const ccssMoney = \(value\) => formatMoney\(value, "CRC"\)/);
assert.doesNotMatch(aguinaldo, /money\(/, "the aguinaldo formats CCSS amounts in CRC");
assert.equal((aguinaldo.match(/ccssMoney\(/g) || []).length, 3);
for (const path of [...walk("users"), ...walk("products/finva")].filter((file) => file.endsWith(".jsx"))) {
  const text = source(path);
  assert.doesNotMatch(text, /currency: ?"CRC", ?currencyDisplay/, `${path} hardcodes a CRC formatter`);
  assert.doesNotMatch(text, /placeholder="₡0"|<b>₡<\/b>/, `${path} hardcodes the ₡ symbol`);
}
console.log("currency tests passed");
