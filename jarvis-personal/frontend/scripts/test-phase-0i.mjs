import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/users/UsersApp.jsx", import.meta.url), "utf8");
const nudge = readFileSync(new URL("../src/users/components/ProgressiveProfileNudge.jsx", import.meta.url), "utf8");
const situation = readFileSync(new URL("../src/users/pages/FinancialSituation.jsx", import.meta.url), "utf8");

assert.match(app, /<ProgressiveProfileNudge/);
assert.match(nudge, /page !== "overview"/);
assert.match(nudge, /sessionStorage/);
assert.match(nudge, /income_count/);
assert.match(nudge, /missing_interest/);
assert.match(nudge, /plan === "vip"/);
assert.match(situation, /monthly_income_average/);
assert.match(situation, /Revisalo antes de guardar/);

console.log("Phase 0I progressive profiling contract passed.");
