import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// A USD bank movement shows its USD amount, never the parser's converted colones,
// and is saved in another base currency only with the user's own rate.
const page = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");
const native = page.slice(page.indexOf("const nativeMoney"), page.indexOf("// One institution"));
const nativeMoney = new Function(`${native.replace("const needsRate", "var needsRate").replace("const nativeMoney", "var nativeMoney")}; return { nativeMoney, needsRate };`)();

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

assert.match(page, /money\(nativeMoney\(item\)\.amount, nativeMoney\(item\)\.currency\)/, "the summary shows the native amount");
assert.doesNotMatch(page, /money\(item\.amount, item\.currency\)/, "the converted amount is never shown as money");
assert.match(page, /defaultValue=\{nativeMoney\(item\)\.amount\}/, "corrections are typed in the native currency");
assert.match(page, /\{needsRate\(item\) && <input name="exchange_rate"[^>]*required/);
assert.match(page, /exchange_rate: needsRate\(item\) \? Number\(form\.get\("exchange_rate"\)\) : null/);
console.log("mail currency tests passed");
