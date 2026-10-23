// Owner exact-amount distribution (web): the amount parser and the wiring of the strategy page.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { EXACT_DISTRIBUTION_MAX, applyExactError, applyExactResult, editExactAmount, parseExactAmount } from "../src/lib/exactDistribution.js";

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

// Valid amounts, in the separators people type; at most two decimals.
for (const [text, value] of [
  ["750000", 750000], ["750.000", 750000], ["750 000", 750000], ["₡750.000", 750000],
  ["750.000,50", 750000.5], ["750,000.50", 750000.5], ["1.234.567,89", 1234567.89], ["12,5", 12.5],
  ["0,01", 0.01], ["1000000000", EXACT_DISTRIBUTION_MAX],
  ["10,555", 10555], ["10.555", 10555],  // one separator and three digits: thousands, never 3 decimals
]) assert.deepEqual(parseExactAmount(text), { value }, text);

// Empty, malformed, zero, negative or too large: refused with a reason, never guessed.
for (const [text, error] of [
  ["", "empty"], ["   ", "empty"], [null, "empty"], ["abc", "format"], ["-5000", "format"], ["1e6", "format"],
  ["1.00.000", "format"], ["12.34.5", "format"], ["750.000,505", "format"],
  ["0", "zero"], ["0,00", "zero"], ["1000000000,01", "too_large"], ["2.000.000.000", "too_large"],
]) assert.deepEqual(parseExactAmount(text), { error }, String(text));

// Wiring: only the Owner's default api carries the exact distribution; VIP Users pass their own.
const page = read("pages/PremiumStrategy.jsx");
const vip = read("users/pages/VipStrategy.jsx");
const api = read("services/jarvisApi.js");
assert.match(page, /getExactDistribution: getJarvisExactDistribution/);
assert.match(page, /const ownerExact = strategy\.scope === "owner" && typeof strategyApi\.getExactDistribution === "function";/);
assert.doesNotMatch(vip, /getExactDistribution|exact-distribution/, "VIP Users never get the exact distribution");
// The amount travels in a POST body, never in a URL.
assert.match(api, /jsonRequest\("\/jarvis\/premium\/strategy-dashboard\/exact-distribution", "POST", \{ amount, currency: "CRC" \}\)/);
// Before a calculation the exact mode shows no figure (never the estimate under the exact label).
assert.match(page, /const showDistribution = !exactMode \|\| Boolean\(exact\.data\?\.strategy\);/);
// The estimate's formula keeps its lines; the exact one shows only the typed amount (no deduction).
assert.match(page, /const distributionBreakdown = manualFormula\r?\n    \? \[\[tx\("Monto que indicaste", "Amount you entered"\), formula\.manual_available\]\]\r?\n    : \[/);
assert.match(page, /tx\("Saldo disponible en MultiMoney", "Available MultiMoney balance"\), formula\.cash_available_now/);

const controls = read("pages/strategy/ExactDistributionControls.jsx");
for (const text of [
  "Aproximada", "Monto exacto", "Puede diferir del dinero que realmente tenés",
  "No registra movimientos ni cambia tus saldos", "Calculado con el monto que indicaste",
  "sin volver a descontar esos pagos", "Monto que te sobra, en colones",
]) assert.ok(controls.includes(text), text);
assert.ok(!controls.includes("superan ese monto"), "an exact amount is never compared with the cycle's obligations");
assert.doesNotMatch(controls, /fetch\(|request\(|jarvisApi/, "the controls never call the API themselves");
// A result never outlives the amount it was calculated from (review defect 4).
const answer = { strategy: { allocation_base_amount: 250000 } };
const shown = applyExactResult({ mode: "exact", amount: "250000", loading: true, error: "", data: null }, "250000", answer);
assert.equal(shown.data, answer);
const edited = editExactAmount(shown, "300000");
assert.equal(edited.data, null, "editing the amount drops the previous result");
assert.equal(edited.amount, "300000");
assert.equal(edited.mode, "exact");
assert.equal(editExactAmount({ ...shown, error: "x" }, "1").error, "");
// A late answer (or error) for an amount the Owner has since changed is ignored.
const late = applyExactResult({ ...edited, loading: true }, "250000", answer);
assert.equal(late.data, null);
assert.equal(late.loading, false);
assert.equal(applyExactError({ ...edited, loading: true }, "250000", "boom").error, "");
assert.equal(applyExactError({ ...edited, loading: true }, "300000", "boom").error, "boom");
assert.match(page, /onAmount=\{\(amount\) => setExact\(\(current\) => editExactAmount\(current, amount\)\)\}/);
assert.match(page, /setExact\(\(current\) => applyExactResult\(current, typed, data\)\)/);

// Review defect 1: the Investments panel reads the estimate only, whatever the distribution mode.
const investments = page.slice(page.indexOf("const renderInvestments = () =>"), page.indexOf("const renderDebts") > 0 ? page.indexOf("const renderDebts") : page.indexOf("const renderDistribution"));
assert.ok(investments.length > 100, "renderInvestments found");
assert.doesNotMatch(investments, /dist[A-Z]\w*/, "no exact-mode value in the Investments panel");
assert.match(investments, /money\(allocationBase\)/);

// Review defect 2: under an exact amount, no note about expenses that reduced the estimate.
assert.match(page, /: exactMode\s*\? tx\("Calculado con el monto que indicaste\.", "Calculated from the amount you entered\."\)\s*: Number\(strategy\.new_expenses_after_cut_count/);

// Review defect 3: the active goal's name comes from the distribution shown.
assert.doesNotMatch(page, /strategy\.goal_portfolio\.active_goal\.name/);
assert.match(page, /distStrategy\.goal_portfolio\.active_goal\.name/);
console.log("exact distribution: ok");
