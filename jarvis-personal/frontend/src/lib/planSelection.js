import { tx } from "./locale.js";

export function isConfirmedPlan(profile, code) {
  return profile?.plan_selected === true &&
    profile?.subscription?.plan === code &&
    profile?.subscription?.status === "active" &&
    !profile?.subscription?.pending_plan;
}

// A downgrade keeps the current plan until its end: the change is confirmed when
// the chosen plan is the scheduled one.
export function isScheduledPlan(profile, code) {
  return profile?.plan_selected === true &&
    profile?.subscription?.status === "active" &&
    profile?.subscription?.pending_plan === code;
}

function isConfirmedChange(response, profile, code) {
  return response?.status === "downgrade_scheduled" ? isScheduledPlan(profile, code) : isConfirmedPlan(profile, code);
}

export async function confirmedPlanProfile(response, code, getMe) {
  if (isConfirmedChange(response, response?.profile, code)) return response.profile;
  const fresh = await getMe();
  if (isConfirmedChange(response, fresh, code)) return fresh;
  throw new Error(tx("El cambio se envió, pero todavía no pudimos confirmar el plan. Revisá tu cuenta antes de intentarlo de nuevo.", "The change was sent, but we couldn’t confirm the plan yet. Check your account before trying again."));
}
