import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");
const card = read("users/components/StrategyOptionalActions.jsx");
const basic = read("users/pages/StrategyBasic.jsx");
const vip = read("users/pages/VipStrategy.jsx");

// P2 is a suggestion only: nothing in the card can trigger an operation.
assert.doesNotMatch(card, /<button|onClick|onSubmit|fetch\(|jarvisApi|request\(/, "no action, button or API call in the suggestion");
assert.match(card, /action\?\.optional === true && action\?\.executes === false && action\?\.source === "excess_savings"/);
// The copy separates it from the monthly plan and carries every warning in ES and EN.
for (const text of [
  "FUERA DEL PLAN MENSUAL", "OUTSIDE THE MONTHLY PLAN",
  "confirmá que no necesitás ese excedente para gastos próximos", "confirm you don't need that excess for upcoming expenses",
  "comisiones por pago anticipado", "early-payment fees",
  "no se puede revertir", "cannot be undone",
  "DINCR no mueve dinero ni registra el pago", "DINCR does not move money or record the payment",
  "no forma parte de tu reparto mensual", "not part of your monthly plan",
]) assert.ok(card.includes(text), text);

// Basic (both branches) and VIP render it, and never merge it into the monthly allocations.
assert.equal((basic.match(/<StrategyOptionalActions actions=\{data\.optional_actions\}/g) || []).length, 2);
assert.match(vip, /<StrategyOptionalActions actions=\{optionalActions\} \/>/);
assert.match(vip, /getStrategyVip\(\)\.then\(\(data\) => \{ if \(active\) setOptionalActions\(data\?\.optional_actions \|\| \[\]\)/);
for (const source of [basic, vip]) {
  assert.doesNotMatch(source, /allocations[^;\n]*optional_actions|optional_actions[^;\n]*allocations/, "never combined with allocations");
  assert.doesNotMatch(source, /strategic_margin[^;\n]*optional|optional[^;\n]*strategic_margin/, "never changes the margin");
}

console.log("DINCR P2 optional suggestion stays separate, informative and non-executable.");
