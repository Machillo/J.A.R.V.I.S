import { tx } from "./locale.js";

export function isConfirmedPlan(profile, code) {
  return profile?.plan_selected === true &&
    profile?.subscription?.plan === code &&
    profile?.subscription?.status === "active";
}

export async function confirmedPlanProfile(response, code, getMe) {
  if (isConfirmedPlan(response?.profile, code)) return response.profile;
  const fresh = await getMe();
  if (isConfirmedPlan(fresh, code)) return fresh;
  throw new Error(tx("El cambio se envió, pero todavía no pudimos confirmar el plan. Revisá tu cuenta antes de intentarlo de nuevo.", "The change was sent, but we couldn’t confirm the plan yet. Check your account before trying again."));
}
