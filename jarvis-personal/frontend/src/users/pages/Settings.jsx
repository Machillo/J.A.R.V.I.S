import { AlertTriangle, Check, CheckCircle2, ChevronRight, Crown, Sparkles, WalletCards, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getBillingCatalog, getMe, getPlans, selectPlan } from "../services/jarvisApi";
import AccountSecurity from "../components/AccountSecurity";
import AppearanceSelector from "../../components/AppearanceSelector";
import AppLockSettings from "../components/AppLockSettings";
import { deviceLanguage } from "../../lib/locale";
import { useFinvaBackHandler } from "../../products/finva/navigation/useFinvaNavigation";
import AccountActions from "../../products/finva/components/AccountActions";
import { confirmedPlanProfile } from "../../lib/planSelection";
import { identifyTelemetryUser, trackEvent } from "../../lib/telemetry";
import LegalLink from "../../components/LegalLink";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const icons = { free: WalletCards, basic: Sparkles, vip: Crown };

export default function Settings({ user, onUserChange, onLogout }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState("");
  const [confirming, setConfirming] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [billing, setBilling] = useState(null);
  const [billingError, setBillingError] = useState("");
  useFinvaBackHandler(() => { if (!changing) setConfirming(""); }, Boolean(confirming));

  const currentPlan = user?.subscription?.plan || "free";
  const currentPlanInfo = useMemo(
    () => plans.find((plan) => plan.code === currentPlan),
    [plans, currentPlan],
  );
  const promotionActive = Boolean(billing?.promotion?.active);

  useEffect(() => {
    let active = true;
    getPlans().then((availablePlans) => { if (active) setPlans(availablePlans); })
      .catch((err) => { if (active) setError(err.message || "No se pudieron cargar los planes."); })
      .finally(() => { if (active) setLoading(false); });
    getBillingCatalog().then((catalog) => { if (active) setBilling(catalog); })
      .catch(() => { if (active) setBillingError("No pudimos confirmar los precios. Reintentá antes de elegir Basic o VIP."); });
    return () => { active = false; };
  }, []);

  const retryBilling = () => {
    setBillingError("");
    getBillingCatalog().then(setBilling)
      .catch(() => setBillingError("No pudimos confirmar los precios. Reintentá antes de elegir Basic o VIP."));
  };


  const openPlanDialog = (planCode) => {
    if (planCode === currentPlan) return;
    if (planCode !== "free" && !billing) { setError("Confirmá los precios antes de elegir un plan de pago."); return; }
    setConfirming(planCode);
    setMessage("");
    setError("");
  };

  const changePlan = async () => {
    const planCode = confirming;
    if (!planCode || planCode === currentPlan) return;
    if (planCode !== "free" && !promotionActive) return;
    setChanging(planCode);
    setError("");
    setMessage("");
    try {
      const response = await selectPlan(planCode, false);
      const activeProfile = await confirmedPlanProfile(response, planCode, getMe);
      identifyTelemetryUser(activeProfile);
      trackEvent("plan_selected", { plan: planCode });
      trackEvent("plan_access_granted", { plan: planCode, access_type: planCode === "free" ? "free" : "promotion" });
      onUserChange?.(activeProfile);
      setConfirming("");
      setMessage(`Plan cambiado a ${activeProfile.subscription.plan.toUpperCase()}.`);
    } catch (err) {
      setError(err.message || "No se pudo cambiar el plan.");
    } finally {
      setChanging("");
    }
  };

  return (
    <section className="mobile-page settings-page">
      <div className="mobile-page-heading">
        <p className="eyebrow">{tx("Cuenta","Account")}</p>
        <h1>{tx("Mi DINCR","My DINCR")}</h1>
        <span>{tx("Administrá tu perfil y el plan que querés probar.", "Manage your profile and the plan you want to try.")}</span>
      </div>

      <div className="account-card">
        <div>
          <strong>{user?.display_name || "Usuario"}</strong>
          <small>{user?.email}</small>
        </div>
        <span className="role-pill">{user?.role}</span>
      </div>

      <AccountSecurity user={user} />

      <AppLockSettings userId={user?.id} />

      <AppearanceSelector />

      <article className="account-card">
        <div><strong>{tx("Información legal","Legal information")}</strong><small>{tx("Consultá los documentos vigentes cuando querás.", "Review the current documents whenever you want.")}</small></div>
        <span><LegalLink kind="terms">{tx("Términos","Terms")}</LegalLink> · <LegalLink kind="privacy">{tx("Privacidad","Privacy")}</LegalLink></span>
      </article>

      <div className="section-heading compact">
        <div>
          <p className="eyebrow">{tx("Suscripción","Subscription")}</p>
          <h2>{tx("Tu plan actual","Your current plan")}</h2>
        </div>
      </div>

      <article className={`current-plan-card plan-${currentPlan}`}>
        <div className="current-plan-icon">
          {currentPlan === "vip" ? <Crown size={24} /> : currentPlan === "basic" ? <Sparkles size={24} /> : <WalletCards size={24} />}
        </div>
        <div className="current-plan-copy">
          <strong>{currentPlanInfo?.name || currentPlan.toUpperCase()}</strong>
          <span>{currentPlanInfo?.tagline || "Plan personal DINCR"}</span>
        </div>
        <span className="plan-status-pill">{tx("Actual","Current")}</span>
      </article>

      <div className="section-heading compact plan-change-heading">
        <div>
          <p className="eyebrow">{tx("Desarrollo", "Development")}</p>
          <h2>{tx("Cambiar de plan","Change plan")}</h2>
          <span>{!billing ? "Estamos confirmando los precios de Basic y VIP." : promotionActive ? "Basic y VIP están gratis hasta el 31 de diciembre de 2026. No habrá cobro automático." : "Las compras de Basic y VIP desde Google Play y App Store estarán disponibles más adelante."}</span>
        </div>
      </div>

      {loading ? (
        <div className="mobile-panel"><p>{tx("Cargando planes...","Loading plans...")}</p></div>
      ) : (
        <div className="settings-plan-list">
          {plans.map((plan) => {
            const Icon = icons[plan.code] || WalletCards;
            const isCurrent = plan.code === currentPlan;
            return (
              <article className={`settings-plan-row ${isCurrent ? "is-current" : ""}`} key={plan.code}>
                <div className="settings-plan-main">
                  <div className={`plan-mini-icon plan-${plan.code}`}><Icon size={20} /></div>
                  <div>
                    <strong>{plan.name}</strong>
                    <small>{plan.tagline}</small>
                  </div>
                </div>

                <ul className="settings-plan-features">{(plan.features || []).map((feature) => <li key={feature}><Check size={15} aria-hidden="true"/>{feature}</li>)}</ul>

                {isCurrent ? (
                  <span className="selected-plan-label"><Check size={16} /> {tx("Seleccionado","Selected")}</span>
                ) : (
                  <button
                    type="button"
                    className="change-plan-button"
                    disabled={Boolean(changing) || (plan.code !== "free" && (!billing || !promotionActive))}
                    onClick={() => openPlanDialog(plan.code)}
                  >
                    <>{tx("Elegir","Choose")} <ChevronRight size={17} /></>
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}

      {billingError && <p className="onboarding-error" role="status">{billingError} <button type="button" onClick={retryBilling}>Reintentar</button></p>}

      {message && <p className="success-banner">{message}</p>}
      {!confirming && error && <p className="onboarding-error">{error}</p>}

      {confirming && confirming !== currentPlan && (() => {
        const selected = plans.find((plan) => plan.code === confirming);
        const SelectedIcon = icons[confirming] || WalletCards;
        return <div className="plan-dialog-backdrop" role="presentation" onMouseDown={(event)=>{if(event.target===event.currentTarget&&!changing)setConfirming("");}}>
          <section className={`plan-dialog plan-${confirming}`} role="dialog" aria-modal="true" aria-labelledby="plan-dialog-title">
            <button className="plan-dialog-close" type="button" aria-label={tx("Cerrar","Close")} disabled={Boolean(changing)} onClick={()=>setConfirming("")}><X size={20}/></button>
            <div className="plan-dialog-icon"><SelectedIcon size={28}/></div>
            <p className="eyebrow">{tx("Confirmar cambio","Confirm change")}</p>
            <h2 id="plan-dialog-title">{tx("Cambiar a", "Switch to")} {selected?.name || confirming.toUpperCase()}</h2>
            <p>{selected?.tagline || "Tu nuevo plan DINCR"}</p>
            {confirming !== "free" && <div className="plan-payment-notice"><CheckCircle2 size={19}/><span>{tx(`Este plan estará gratis hasta el 31 de diciembre de 2026. Desde enero su precio previsto será ${confirming === "basic" ? "₡2.990" : "₡4.990"}/mes, sin cobro automático.`, `This plan will be free until December 31, 2026. From January its planned price will be ${confirming === "basic" ? "₡2,990" : "₡4,990"}/month, with no automatic charge.`)}</span></div>}
            {error && <div className="plan-dialog-error"><AlertTriangle size={18}/><span>{error}</span></div>}
            <div className="plan-dialog-actions"><button type="button" className="plan-dialog-cancel" disabled={Boolean(changing)} onClick={()=>setConfirming("")}>{tx("Cancelar","Cancel")}</button><button type="button" className="plan-dialog-confirm" disabled={Boolean(changing)} onClick={changePlan}>{changing ? tx("Procesando...","Processing...") : `${tx("Confirmar","Confirm")} ${selected?.name || confirming.toUpperCase()}`}</button></div>
          </section>
        </div>;
      })()}

      <AccountActions onLogout={onLogout} variant={currentPlan} />
    </section>
  );
}
