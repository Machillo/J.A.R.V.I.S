import { tx } from "../locale.js";

const PLAN_NAMES = { free: ["Gratis", "Free"], basic: ["Basic", "Basic"], vip: ["VIP", "VIP"] };
const planName = (plan) => tx(...(PLAN_NAMES[plan] || PLAN_NAMES.free));

/** What to tell the user after a store action. `plan` is the plan the backend reports. */
export function outcomeMessage(outcome, { plan, context = "purchase" } = {}) {
  switch (outcome) {
    case "verified":
      return plan && plan !== "free"
        ? { tone: "success", text: tx(`Compra confirmada. Tu plan es ${planName(plan)}.`, `Purchase confirmed. Your plan is ${planName(plan)}.`) }
        : { tone: "warning", text: tx("La tienda no confirmó una suscripción activa para esta compra.", "The store didn’t confirm an active subscription for this purchase.") };
    case "pending":
      return { tone: "info", text: tx("Tu pago quedó pendiente en la tienda. Activaremos el plan cuando la tienda lo confirme.", "Your payment is pending in the store. We’ll activate the plan once the store confirms it.") };
    case "cancelled":
      return { tone: "info", text: context === "restore"
        ? tx("Restauración cancelada.", "Restore cancelled.")
        : tx("Compra cancelada. No se hizo ningún cobro.", "Purchase cancelled. You weren’t charged.") };
    case "conflict":
      return { tone: "warning", text: tx("Esta compra pertenece a otra cuenta DINCR. Iniciá sesión con esa cuenta para usarla.", "This purchase belongs to another DINCR account. Sign in with that account to use it.") };
    case "rejected":
      return { tone: "error", text: tx("No pudimos validar esta compra con la tienda. Si ves un cobro, escribinos a soporte.", "We couldn’t validate this purchase with the store. If you see a charge, contact support.") };
    case "disabled":
      return { tone: "info", text: tx("Las compras desde la app todavía no están disponibles.", "In-app purchases aren’t available yet.") };
    case "unavailable":
      return { tone: "warning", text: tx("La tienda no está disponible en este dispositivo en este momento.", "The store isn’t available on this device right now.") };
    case "unknown_product":
      return { tone: "error", text: tx("Este producto no corresponde a un plan DINCR.", "This product isn’t a DINCR plan.") };
    case "session":
      return { tone: "error", text: tx("Tu sesión venció. Iniciá sesión nuevamente.", "Your session expired. Please sign in again.") };
    case "already_subscribed":
      return { tone: "info", text: tx("Ya tenés una suscripción activa en la tienda. Para cambiar de plan, usá «Gestionar suscripción».", "You already have an active store subscription. To change plans, use “Manage subscription”.") };
    case "busy":
      return { tone: "info", text: tx("Ya hay una operación de la tienda en curso.", "A store operation is already in progress.") };
    case "network":
    case "backend":
    case "malformed":
      // The store may have charged: never say it failed; recovery sends it again.
      return context === "purchase"
        ? { tone: "warning", text: tx("No pudimos confirmar tu compra con DINCR todavía. La reintentaremos automáticamente; también podés usar «Restaurar compras».", "We couldn’t confirm your purchase with DINCR yet. We’ll retry automatically; you can also use “Restore purchases”.") }
        : { tone: "error", text: tx("No pudimos restaurar tus compras. Intentá nuevamente.", "We couldn’t restore your purchases. Please try again.") };
    case "store":
    default:
      return { tone: "error", text: tx("La tienda no pudo completar la compra. Intentá nuevamente.", "The store couldn’t complete the purchase. Please try again.") };
  }
}

/** Summary after "Restaurar compras" (per-purchase results from the backend). */
export function restoreMessage(result, plan) {
  if (result?.outcome !== "restored") return outcomeMessage(result?.outcome, { context: "restore" });
  const outcomes = (result.results || []).map((item) => item.outcome);
  if (!outcomes.length) return { tone: "info", text: tx("No encontramos suscripciones de esta tienda para restaurar.", "We didn’t find subscriptions from this store to restore.") };
  if (outcomes.includes("conflict") && !outcomes.includes("verified")) return outcomeMessage("conflict");
  if (outcomes.includes("verified")) {
    return plan && plan !== "free"
      ? { tone: "success", text: tx(`Compras restauradas. Tu plan es ${planName(plan)}.`, `Purchases restored. Your plan is ${planName(plan)}.`) }
      : { tone: "info", text: tx("Revisamos tus compras: ninguna suscripción está activa ahora.", "We checked your purchases: no subscription is active right now.") };
  }
  return outcomeMessage(outcomes[0], { context: "restore" });
}
