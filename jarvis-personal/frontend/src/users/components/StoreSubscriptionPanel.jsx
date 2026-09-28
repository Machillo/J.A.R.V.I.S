import { AlertTriangle, CheckCircle2, Info, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getStoreEntitlement } from "../services/jarvisApi";
import { liveStoreSubscription, storeBilling } from "../../lib/storeBilling";
import { outcomeMessage, restoreMessage } from "../../lib/storeBilling/messages";
import { deviceLanguage } from "../../lib/locale";

const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;
const PERIOD = { monthly: ["por mes", "per month"], annual: ["por año", "per year"] };
const PLAN = { basic: "Basic", vip: "VIP" };
const STORE = { ios: "App Store", android: "Google Play" };
const TONE_ICON = { success: CheckCircle2, info: Info, warning: AlertTriangle, error: AlertTriangle };

// Buying Basic / VIP through the App Store or Google Play (native app only). The plan
// shown afterwards is always the one the backend reports (onUserChange with /auth/me).
export default function StoreSubscriptionPanel({ user, onUserChange }) {
  const [billing, setBilling] = useState(null);
  const [offers, setOffers] = useState([]);
  const [phase, setPhase] = useState("loading");
  const [notice, setNotice] = useState(null);
  const [storeSubscription, setStoreSubscription] = useState(null);
  // The backend accepts store purchases (customer token issued; 503 while switched off).
  const [open, setOpen] = useState(false);

  const applyResult = useCallback((result) => {
    if (result?.profile) onUserChange?.(result.profile);
    if (result?.entitlement) setStoreSubscription(liveStoreSubscription(result.entitlement));
  }, [onUserChange]);

  const load = useCallback(async () => {
    setPhase("loading");
    setNotice(null);
    setOpen(false);
    const service = await storeBilling();
    if (!service) { setPhase("web"); return; }
    setBilling(service);
    getStoreEntitlement().then((state) => setStoreSubscription(liveStoreSubscription(state))).catch(() => {});
    const availability = await service.availability();
    if (availability !== "available") {
      setNotice(outcomeMessage(availability));
      setPhase("closed");
      return;
    }
    setOpen(true);
    try {
      const loaded = await service.loadOffers();
      setOffers(loaded);
      setPhase(loaded.length ? "ready" : "closed");
      if (!loaded.length) setNotice(outcomeMessage("unavailable"));
    } catch (error) {
      setNotice(outcomeMessage(error.kind || "unavailable"));
      setPhase("closed");
    }
  }, []);

  useEffect(() => {
    let active = true;
    load().catch(() => { if (active) { setNotice(outcomeMessage("unavailable")); setPhase("closed"); } });
    const onRecovered = (event) => applyResult(event.detail);
    window.addEventListener("dincr:store-entitlement", onRecovered);
    return () => { active = false; window.removeEventListener("dincr:store-entitlement", onRecovered); };
  }, [load, applyResult]);

  if (phase === "web" || user?.role !== "user") return null;

  const working = ["store", "verifying", "restoring"].includes(phase);

  const buy = async (offer) => {
    if (!billing || working) return;
    setNotice(null);
    const result = await billing.purchase(offer, { onStage: setPhase }).catch(() => ({ outcome: "store" }));
    applyResult(result);
    const plan = result?.profile?.subscription?.plan;
    setNotice(outcomeMessage(result.outcome, { plan, context: "purchase" }));
    if (result.outcome === "disabled") setOpen(false);
    setPhase(result.outcome === "disabled" ? "closed" : "ready");
  };

  const restore = async () => {
    if (!billing || working) return;
    setNotice(null);
    setPhase("restoring");
    const result = await billing.restore().catch(() => ({ outcome: "backend", results: [] }));
    applyResult(result);
    setNotice(restoreMessage(result, result?.profile?.subscription?.plan));
    if (result.outcome === "disabled") setOpen(false);
    setPhase(result.outcome === "disabled" ? "closed" : offers.length ? "ready" : "closed");
  };

  const NoticeIcon = notice ? TONE_ICON[notice.tone] || Info : null;
  const store = STORE[billing?.platform] || tx("la tienda", "the store");

  return (
    <article className="mobile-panel store-subscription-panel" aria-busy={working}>
      <div className="store-subscription-heading">
        <strong>{tx(`Suscribite con ${store}`, `Subscribe with ${store}`)}</strong>
        <small>{tx("El cobro lo hace la tienda. DINCR activa tu plan cuando la tienda lo confirma.", "The store handles the payment. DINCR activates your plan once the store confirms it.")}</small>
      </div>

      {storeSubscription && (
        <p className="store-subscription-current">
          {tx(
            `Suscripción activa en la tienda: ${PLAN[storeSubscription.entitlement]} ${storeSubscription.billing_period === "annual" ? "anual" : "mensual"}.`,
            `Active store subscription: ${PLAN[storeSubscription.entitlement]} ${storeSubscription.billing_period === "annual" ? "annual" : "monthly"}.`,
          )}
        </p>
      )}

      {user?.subscription?.access_source === "courtesy" && phase === "ready" && (
        <p className="store-subscription-note">{tx("Tu acceso actual es promocional. Si te suscribís, la tienda empieza a cobrar desde la compra.", "Your current access is promotional. If you subscribe, the store starts charging from the purchase.")}</p>
      )}

      {storeSubscription && phase === "ready" && (
        <p className="store-subscription-note">{tx("Para cambiar de plan o de período, usá «Gestionar suscripción» en la tienda.", "To change plan or period, use “Manage subscription” in the store.")}</p>
      )}

      {phase === "loading" && <p>{tx("Cargando precios de la tienda...", "Loading store prices...")}</p>}
      {phase === "store" && <p role="status">{tx("Compra en progreso en la tienda...", "Purchase in progress in the store...")}</p>}
      {phase === "verifying" && <p role="status">{tx("Verificando tu compra con DINCR...", "Verifying your purchase with DINCR...")}</p>}
      {phase === "restoring" && <p role="status">{tx("Restaurando compras...", "Restoring purchases...")}</p>}

      {notice && (
        <div className={`store-subscription-notice tone-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
          <NoticeIcon size={18} aria-hidden="true" /><span>{notice.text}</span>
        </div>
      )}

      {open && offers.length > 0 && phase !== "closed" && (
        <ul className="store-subscription-offers">
          {offers.map((offer) => (
            <li key={offer.productId}>
              <div>
                <strong>{PLAN[offer.plan]}</strong>
                <small>{offer.priceString} {tx(...PERIOD[offer.period])}</small>
              </div>
              <button
                type="button"
                className="change-plan-button"
                disabled={working || Boolean(storeSubscription)}
                onClick={() => buy(offer)}
              >
                {tx("Suscribirme", "Subscribe")}
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && phase !== "loading" && (
        <div className="store-subscription-actions">
          <button type="button" className="plan-dialog-cancel" disabled={working} onClick={restore}>
            <RotateCcw size={16} aria-hidden="true" /> {tx("Restaurar compras", "Restore purchases")}
          </button>
          {storeSubscription && (
            <button type="button" className="plan-dialog-cancel" disabled={working} onClick={() => billing.manage().catch(() => {})}>
              {tx("Gestionar suscripción", "Manage subscription")}
            </button>
          )}
        </div>
      )}
    </article>
  );
}
