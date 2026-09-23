import assert from "node:assert/strict";
import { confirmedPlanProfile, isConfirmedPlan } from "../src/lib/planSelection.js";

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
    /no pudimos confirmar el plan/,
  );
}

console.log("Free, Basic and VIP plan confirmation contracts passed.");
