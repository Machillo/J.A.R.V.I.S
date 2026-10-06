import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// A debt's unknown interest rate (debts.interest_rate_known false, or no rate) is never 0% in the
// Capacitor Users app: Debts shows it as not recorded, makes no payoff estimate from it, opens the
// edit field empty, and an edit confirms the rate only when the user changed it. The VIP advisory
// card shows it as not recorded. Synthetic data.
const debts = readFileSync(new URL("../src/users/pages/Debts.jsx", import.meta.url), "utf8");
const helpers = debts.slice(debts.indexOf("const rateUnknown"), debts.indexOf("function DebtFields"));
const { rateText, editableRate, monthsLeft } = new Function("tx", `${helpers}; return { rateText, editableRate, monthsLeft };`)((es) => es);

const historicalZero = { remaining_amount: 120000, monthly_payment: 10000, interest_rate: 0, interest_rate_known: false };
const noRate = { remaining_amount: 120000, monthly_payment: 10000, interest_rate: null, interest_rate_known: false };
const knownZero = { remaining_amount: 120000, monthly_payment: 10000, interest_rate: 0, interest_rate_known: true };
const known = { remaining_amount: 120000, monthly_payment: 10000, interest_rate: 24, interest_rate_known: true };

for (const unknown of [historicalZero, noRate]) {
  assert.equal(rateText(unknown), "Sin registrar", "an unknown rate is never shown as 0%");
  assert.equal(editableRate(unknown), "", "the edit field starts empty, never 0");
  assert.equal(monthsLeft(unknown), null, "no payoff estimate from an unknown rate");
}
assert.equal(rateText(knownZero), "0%", "a known 0% is still 0%");
assert.equal(editableRate(knownZero), "0");
assert.equal(monthsLeft(knownZero), 12);
assert.equal(rateText(known), "24%");
assert.equal(editableRate(known), "24");
assert.ok(monthsLeft(known) > 12, "a known rate still shapes the estimate");

// The confirmation is the field changing from what the form opened with (the server keeps a loaded value).
assert.match(debts, /const interest_rate_confirmed = String\(edit\.interest_rate \?\? ""\)\.trim\(\) !== editRate\.trim\(\);/);
assert.match(debts, /updateDebt\(edit\.id,\{\.\.\.payload\(edit\),interest_rate_confirmed\}\)/);
assert.match(debts, /setEditRate\(rate\); setEdit\(\{\.\.\.debt,interest_rate:rate\}\)/);
assert.doesNotMatch(debts, /Number\(selected\.interest_rate \|\| 0\)/, "the detail never turns an unknown rate into 0%");

const advisory = readFileSync(new URL("../src/pages/PremiumStrategy.jsx", import.meta.url), "utf8");
assert.match(advisory, /debt\.interest_rate == null \? tx\("Sin registrar", "Not recorded"\)/);
assert.doesNotMatch(advisory, /Number\(debt\.interest_rate \|\| 0\)/, "the advisory never shows an unknown rate as 0.00%");

console.log("Debt rates: unknown is shown as not recorded, never 0%; a known 0% stays 0%; edits confirm only a changed rate.");
