// Owner exact-amount distribution (web): the amount parser and the wiring of the strategy page.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { EXACT_DISTRIBUTION_MAX, parseExactAmount } from "../src/lib/exactDistribution.js";

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
// The estimate's formula keeps its lines; the exact one shows the typed amount instead.
assert.match(page, /tx\("Monto que indicaste", "Amount you entered"\), formula\.manual_available/);
assert.match(page, /tx\("Saldo disponible en MultiMoney", "Available MultiMoney balance"\), formula\.cash_available_now/);

const controls = read("pages/strategy/ExactDistributionControls.jsx");
for (const text of [
  "Aproximada", "Monto exacto", "Puede diferir del dinero que realmente tenés",
  "No registra movimientos ni cambia tus saldos", "Calculado con el monto que indicaste",
  "superan ese monto", "Monto disponible en colones",
]) assert.ok(controls.includes(text), text);
assert.doesNotMatch(controls, /fetch\(|request\(|jarvisApi/, "the controls never call the API themselves");
console.log("exact distribution: ok");
