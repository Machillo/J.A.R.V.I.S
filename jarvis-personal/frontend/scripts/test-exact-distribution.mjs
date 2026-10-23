// Owner exact-amount distribution (web): the amount parser and the wiring of the strategy page.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  EXACT_DISTRIBUTION_MAX, applyExactError, applyExactResult, distributionPanel, editExactAmount, investmentPanel, parseExactAmount,
} from "../src/lib/exactDistribution.js";

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
// The page renders the panels from these functions (behaviour tested below with real-shaped data).
assert.match(page, /const investment = investmentPanel\(strategy\);/);
assert.match(page, /const panel = distributionPanel\(\{ strategy, exact, ownerExact \}\);/);
assert.match(page, /money\(investment\.base\)/);
assert.match(page, /\[panel\.note\]\(\)/);

const controls = read("pages/strategy/ExactDistributionControls.jsx");
for (const text of [
  "Aproximada", "Monto exacto", "Puede diferir del dinero que realmente tenés",
  "Calcular no registra nada: solo CONFIRMAR registra los movimientos", "Calculado con el monto que indicaste",
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

// --- Panels, with an estimate and an exact answer that differ in every field -------------------
const estimate = {
  scope: "owner", allocation_base_amount: 500000, investment_recommended: 120000, new_expenses_after_cut_count: 2,
  allocation_items: [{ key: "ataque_de_deuda", amount: 380000 }, { key: "inversion", amount: 120000 }],
  allocation_amounts: { ataque_de_deuda: 380000, inversion: 120000 },
  distribution_formula: { cash_available_now: 300000, income: 900000, statement_spending: 100000, new_spending_after_cut: 50000,
    debt_commitment: 400000, mandatory_fixed_pending: 150000, surplus: 500000, deficit: 0 },
  goal_portfolio: { active_goal: { name: "Meta del estimado" } }, primary_debt_name: "Deuda del estimado",
};
const exactAnswer = {
  scope: "owner", distribution_source: "manual_amount", allocation_base_amount: 250000, investment_recommended: 0,
  allocation_items: [{ key: "meta_prioritaria", amount: 100000 }, { key: "fondo_de_emergencia", amount: 150000 }],
  allocation_amounts: { meta_prioritaria: 100000, fondo_de_emergencia: 150000 },
  distribution_formula: { manual_available: 250000, surplus: 250000 },
  goal_portfolio: { active_goal: { name: "Meta del monto exacto" } }, primary_debt_name: "Deuda del monto exacto",
};
const exactState = { mode: "exact", amount: "250000", loading: false, error: "", data: { strategy: exactAnswer } };

// Defect 1: the Investments panel reads the estimate, even with an exact answer on screen.
const investment = investmentPanel(estimate);
assert.deepEqual(investment, { base: 500000, recommended: 120000, state: "ready" });
const exactPanel = distributionPanel({ strategy: estimate, exact: exactState, ownerExact: true });
assert.equal(exactPanel.base, 250000, "the Distribution panel shows the exact base");
assert.notEqual(investment.base, exactPanel.base, "the two panels never share the exact base");
assert.equal(investmentPanel({ allocation_base_amount: 0 }).state, "blocked");
assert.equal(investmentPanel({ allocation_base_amount: 10, investment_recommended: 0 }).state, "limited");

// Defect 2: under an exact amount the note is "exact", never the estimate's new-expenses note.
assert.equal(exactPanel.note, "exact");
const estimatePanel = distributionPanel({ strategy: estimate, exact: { ...exactState, mode: "estimate" }, ownerExact: true });
assert.equal(estimatePanel.note, "new_expenses");
assert.equal(estimatePanel.newExpensesCount, 2);
assert.equal(distributionPanel({ strategy: { ...estimate, new_expenses_after_cut_count: 0 }, exact: null, ownerExact: true }).note, "recalculated");
assert.equal(distributionPanel({ strategy: { ...estimate, distribution_formula: { ...estimate.distribution_formula, deficit: 5 } }, exact: null, ownerExact: true }).note, "deficit");

// Defect 3: the active goal and the target debt come from the distribution shown.
assert.equal(exactPanel.activeGoalName, "Meta del monto exacto");
assert.equal(exactPanel.primaryDebtName, "Deuda del monto exacto");
assert.equal(estimatePanel.activeGoalName, "Meta del estimado");
const goalOnlyInExact = distributionPanel({ strategy: { ...estimate, goal_portfolio: {} }, exact: exactState, ownerExact: true });
assert.equal(goalOnlyInExact.activeGoalName, "Meta del monto exacto", "no crash when only the exact answer has a goal");
assert.equal(distributionPanel({ strategy: estimate, exact: { ...exactState, data: { strategy: { ...exactAnswer, goal_portfolio: {} } } }, ownerExact: true }).activeGoalName, null);

// The exact answer lists only the typed amount; the estimate keeps its deduction lines.
assert.deepEqual(exactPanel.breakdownKeys, ["manual_available"]);
assert.equal(exactPanel.addedLines, 1);
assert.equal(exactPanel.deficit, 0);
assert.ok(exactPanel.balanced);
assert.deepEqual(estimatePanel.breakdownKeys, ["cash_available_now", "income", "statement_spending", "new_spending_after_cut", "debt_commitment", "mandatory_fixed_pending"]);
assert.equal(estimatePanel.base, 500000);

// Defect 4 through the panel: before a calculation, and after editing the amount, no figure shows.
assert.equal(distributionPanel({ strategy: estimate, exact: { ...exactState, data: null }, ownerExact: true }).showDistribution, false);
const afterEdit = distributionPanel({ strategy: estimate, exact: editExactAmount(exactState, "300000"), ownerExact: true });
assert.equal(afterEdit.showDistribution, false, "an edited amount never shows the previous result");
// Not the Owner: an exact answer is never read.
const vipPanel = distributionPanel({ strategy: estimate, exact: exactState, ownerExact: false });
assert.equal(vipPanel.exactMode, false);
assert.equal(vipPanel.base, 500000);

console.log("exact distribution: ok");

// CONFIRMAR (web): one key per result, the reviewed split is what is sent, confirmed once.
{
  const { applyConfirmation, canConfirmExact, confirmExactPayload } = await import("../src/lib/exactDistribution.js");
  const data = {
    strategy: { allocation_items: [{ key: "ataque_de_deuda", amount: 114614.1 }, { key: "fondo_de_emergencia", amount: 101879.2 }, { key: "vida_controlada", amount: 38204.7 }] },
    confirmation_plan: { confirmable: true, blocking_reasons: [], steps: [], fingerprint: "f".repeat(64) },
  };
  const typed = editExactAmount({ mode: "exact", amount: "" }, "254698");
  assert.equal(canConfirmExact(typed), false, "nothing to confirm before a result");
  const shown = applyExactResult(typed, "254698", data, "confirm-web-0001");
  assert.equal(canConfirmExact(shown), true);
  assert.deepEqual(confirmExactPayload(shown, 254698), {
    amount: 254698, currency: "CRC", confirmation_key: "confirm-web-0001",
    expected_items: [{ key: "ataque_de_deuda", amount: 114614.1 }, { key: "fondo_de_emergencia", amount: 101879.2 }, { key: "vida_controlada", amount: 38204.7 }],
    plan_fingerprint: "f".repeat(64),
  });
  assert.equal(confirmExactPayload({ ...shown, data: { ...data, confirmation_plan: { confirmable: true } } }, 254698), null,
    "no CONFIRMAR without the reviewed plan's fingerprint");
  assert.notEqual(applyExactResult(typed, "254698", data).confirmationKey, applyExactResult(typed, "254698", data).confirmationKey, "a new result gets a new key");
  assert.equal(canConfirmExact(applyConfirmation(shown, "another-key", { status: "applied" })), true, "an answer for another result is ignored");
  const confirmed = applyConfirmation(shown, "confirm-web-0001", { status: "applied" });
  assert.equal(canConfirmExact(confirmed), false, "confirmed once: no second CONFIRMAR");
  const edited = editExactAmount(confirmed, "300000");
  assert.equal(edited.confirmationKey, null);
  assert.equal(confirmExactPayload(edited, 300000), null);
  const blocked = applyExactResult(typed, "254698", { ...data, confirmation_plan: { confirmable: false, blocking_reasons: ["x"], steps: [] } });
  assert.equal(canConfirmExact(blocked), false, "a plan that cannot be recorded offers no CONFIRMAR");
  // The confirmation travels in a POST body to the Owner route, and only the Owner's api has it.
  assert.match(api, /jsonRequest\("\/jarvis\/premium\/strategy-dashboard\/exact-distribution\/confirm", "POST", payload\)/);
  assert.match(page, /confirmExactDistribution: confirmJarvisExactDistribution/);
  assert.doesNotMatch(vip, /confirmExactDistribution|exact-distribution\/confirm/, "VIP Users never confirm a distribution");
}

console.log("exact distribution confirm: ok");
