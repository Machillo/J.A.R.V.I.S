import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { formatKnownMoney, formatMoney, setBaseCurrency } from "../src/lib/currency.js";
import { codeLabel } from "../src/lib/locale.js";

// UX-6: the VIP command center sends null for a figure it doesn't know (safe to spend, monthly
// margin, 45-day minimum), a director priority "incomplete" and an empty roadmap when the inputs
// are missing. The app never turns that into ₡0, a raw code or "0 acciones".
setBaseCurrency("CRC");
assert.equal(formatKnownMoney(null), "—", "unknown is not ₡0");
assert.equal(formatKnownMoney(undefined), "—");
assert.equal(formatKnownMoney(0), formatMoney(0), "a known zero is still ₡0");
assert.equal(formatKnownMoney(250000), formatMoney(250000));

for (const language of ["es", "en"]) {
  const label = codeLabel("vipPriorities", "incomplete", language);
  assert.notEqual(label, "incomplete", `${language}: the priority code is never shown raw`);
}
assert.equal(codeLabel("vipPriorities", "incomplete", "es"), "Falta información");

const vip = readFileSync(new URL("../src/products/finva/features/vip/VipScreens.jsx", import.meta.url), "utf8");
// The figures that can be null are formatted as unknown, never through formatMoney's ₡0.
assert.match(vip, /title=\{knownMoney\(data\.safe_to_spend\?\.amount\)\}/);
assert.doesNotMatch(vip, /\bmoney\(data\.safe_to_spend/, "no command-center figure through formatMoney");
assert.doesNotMatch(vip, /Number\(data\.safe_to_spend\?\.monthly_margin\) \|\| 0/, "a null margin is never read as 0");
// An empty roadmap says DINCR needs information, never "encontró 0 acciones".
assert.match(vip, /caption=\{roadmap\.length \? tx\(`DINCR encontró/);
assert.match(vip, /DINCR necesita más información para calcular esto\./);

console.log("VIP unknown figures stay unknown: no ₡0, no raw priority code, no 0 actions.");
