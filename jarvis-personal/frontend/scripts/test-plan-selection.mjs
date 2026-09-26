import assert from "node:assert/strict";
import { confirmedPlanProfile, isConfirmedPlan, isScheduledPlan } from "../src/lib/planSelection.js";

for (const code of ["free", "basic", "vip"]) {
  const active = { plan_selected: true, subscription: { plan: code, status: "active" } };
  assert.equal(isConfirmedPlan(active, code), true);
  assert.equal(await confirmedPlanProfile({ profile: active }, code, () => {
    throw new Error("No hace falta una segunda consulta después de guardar.");
  }), active);

  const stale = { plan_selected: false, subscription: { plan: "free", status: "active" } };
  assert.equal(await confirmedPlanProfile({ profile: stale }, code, async () => active), active);
  assert.equal(isConfirmedPlan({ ...active, subscription: { plan: code, status: "payment_pending" } }, code), false);
  await assert.rejects(
    confirmedPlanProfile({ profile: stale }, code, async () => ({ ...active, subscription: { plan: "free", status: "pending" } })),
    /no pudimos confirmar el plan|couldn’t confirm the plan/,
  );
}

// A downgrade keeps the current plan until its end: the scheduled plan confirms the change.
const vipUntilEnd = { plan_selected: true, subscription: { plan: "vip", status: "active", pending_plan: "free", pending_effective_at: "2027-01-01T06:00:00Z" } };
assert.equal(isConfirmedPlan(vipUntilEnd, "free"), false, "a scheduled downgrade is not an immediate plan change");
assert.equal(isConfirmedPlan(vipUntilEnd, "vip"), false, "a pending change is not a confirmed keep");
assert.equal(isScheduledPlan(vipUntilEnd, "free"), true);
assert.equal(await confirmedPlanProfile({ status: "downgrade_scheduled", profile: vipUntilEnd }, "free", () => {
  throw new Error("The scheduled response is already confirmed.");
}), vipUntilEnd);
await assert.rejects(
  confirmedPlanProfile({ status: "downgrade_scheduled", profile: vipUntilEnd }, "basic", async () => vipUntilEnd),
  /no pudimos confirmar el plan|couldn’t confirm the plan/,
);
const kept = { plan_selected: true, subscription: { plan: "vip", status: "active", pending_plan: null } };
assert.equal(await confirmedPlanProfile({ status: "plan_kept", profile: kept }, "vip", () => {
  throw new Error("Keeping the plan is confirmed by the response.");
}), kept);

// The Settings screen must never present a downgrade as an immediate change.
const settings = await import("node:fs").then((fs) => fs.readFileSync(new URL("../src/users/pages/Settings.jsx", import.meta.url), "utf8"));
for (const needle of ["downgrade_scheduled", "pending_plan", "pending_effective_at", "Mantener"]) {
  assert.ok(settings.includes(needle), `Settings must handle ${needle}`);
}

console.log("Free, Basic and VIP plan confirmation contracts passed (including scheduled downgrades).");
