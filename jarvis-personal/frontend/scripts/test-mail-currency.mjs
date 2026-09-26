import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// A USD bank movement shows its USD amount, never the parser's converted colones,
// and is saved in another base currency only with the user's own rate.
const page = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");
const native = page.slice(page.indexOf("const upper = "), page.indexOf("// One institution"));
const nativeMoney = new Function(`${native.replaceAll("const ", "var ")}; return { nativeMoney, needsRate, cannotConvert };`)();

const bac = { amount: 10395, currency: "CRC", original_amount: 21, original_currency: "USD", account_base_currency: "CRC" };
const multimoney = { amount: 50, currency: "CRC", original_amount: 50, original_currency: "USD", account_base_currency: "CRC" };
const colones = { amount: 18500, currency: "CRC", original_amount: null, original_currency: null, account_base_currency: "CRC" };
assert.deepEqual(nativeMoney.nativeMoney(bac), { amount: 21, currency: "USD" });
assert.deepEqual(nativeMoney.nativeMoney(multimoney), { amount: 50, currency: "USD" }, "$50 is not ₡50");
assert.deepEqual(nativeMoney.nativeMoney(colones), { amount: 18500, currency: "CRC" });
assert.equal(nativeMoney.needsRate(bac), true);
assert.equal(nativeMoney.needsRate(colones), false);
assert.equal(nativeMoney.needsRate({ ...bac, account_base_currency: "USD" }), false);
assert.equal(nativeMoney.needsRate({ ...colones, account_base_currency: "USD" }), true);
// A legacy base (EUR) cannot be converted: no rate field, an explicit note instead.
assert.equal(nativeMoney.needsRate({ ...colones, account_base_currency: "EUR" }), false);
assert.equal(nativeMoney.cannotConvert({ ...colones, account_base_currency: "EUR" }), true);
assert.equal(nativeMoney.cannotConvert(colones), false);
assert.deepEqual(nativeMoney.nativeMoney({ ...bac, original_currency: "usd" }), { amount: 21, currency: "USD" });

assert.match(page, /money\(nativeMoney\(item\)\.amount, nativeMoney\(item\)\.currency\)/, "the summary shows the native amount");
assert.doesNotMatch(page, /money\(item\.amount, item\.currency\)/, "the converted amount is never shown as money");
assert.match(page, /defaultValue=\{nativeMoney\(item\)\.amount\}/, "corrections are typed in the native currency");
assert.match(page, /\{needsRate\(item\) && <input name="exchange_rate"[^>]*required/);
assert.match(page, /exchange_rate: needsRate\(item\) \? Number\(form\.get\("exchange_rate"\)\) : null/);
console.log("mail currency tests passed");
