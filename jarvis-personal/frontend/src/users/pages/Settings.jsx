import { AlertTriangle, Check, CheckCircle2, ChevronRight, Crown, Sparkles, WalletCards, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getBillingCatalog, getMe, getPlans, selectPlan } from "../services/jarvisApi";
import AccountSecurity from "../components/AccountSecurity";
import AppearanceSelector from "../../components/AppearanceSelector";
import AppLockSettings from "../components/AppLockSettings";
import { codeLabel, deviceLanguage } from "../../lib/locale";
import { useFinvaBackHandler } from "../../products/finva/navigation/useFinvaNavigation";
import AccountActions from "../../products/finva/components/AccountActions";
import { confirmedPlanProfile } from "../../lib/planSelection";
import { identifyTelemetryUser, trackEvent } from "../../lib/telemetry";
import LegalLink from "../../components/LegalLink";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const icons = { free: WalletCards, basic: Sparkles, vip: Crown };
const ROLE_LABELS = { owner: ["Propietario", "Owner"], admin: ["Administrador", "Admin"], user: ["Usuario", "User"] };
const roleLabel = (role) => ROLE_LABELS[role] ? tx(...ROLE_LABELS[role]) : role;
const PLAN_RANK = { free: 1, basic: 2, vip: 3 };
// Access ends at a stored instant; show the last day it still includes, in Costa Rica time
// (the launch promotion ends 2027-01-01 06:00 UTC, which is "until December 31, 2026").
const planDate = (value) => value
  ? new Date(Date.parse(value) - 1).toLocaleDateString(language === "es" ? "es-CR" : "en-US", { day: "numeric", month: "long", year: "numeric", timeZone: "America/Costa_Rica" })
  : "";

function PlanChangeNotice({ confirming, currentPlan, pendingPlan, accessEndDate, planName, isDowngrade }) {
  const current = planName(currentPlan);
  const next = planName(confirming);
  if (confirming === currentPlan) {
    return <div className="plan-payment-notice"><CheckCircle2 size={19}/><span>{tx(`Cancelamos el cambio a ${planName(pendingPlan)} y seguís con ${current}.`, `We cancel the change to ${planName(pendingPlan)} and you keep ${current}.`)}</span></div>;
  }
  if (!isDowngrade(confirming)) return null;
  const until = accessEndDate
    ? tx(`Seguís con ${current} y todos sus beneficios hasta el ${accessEndDate}.`, `You keep ${current} and all its benefits until ${accessEndDate}.`)
    : tx(`Si tu plan ${current} tiene un período vigente, lo conservás hasta que termine.`, `If your ${current} plan has a current period, you keep it until it ends.`);
  const then = confirming === "free"
    ? tx("Después pasás a Gratis.", "Then you move to Free.")
    : tx(`Después pasás a ${next} si tenés una compra activa de ${next}; si no, a Gratis.`, `Then you move to ${next} if you have an active ${next} purchase; otherwise to Free.`);
  return <div className="plan-payment-notice"><CheckCircle2 size={19}/><span>{until} {then}</span></div>;
}
const pricesUnavailable = () => tx("No pudimos confirmar los precios. Reintentá antes de elegir Basic o VIP.", "We couldn’t confirm prices. Retry before choosing Basic or VIP.");

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
  // A downgrade keeps the current plan until its end; the backend owns the dates.
  const pendingPlan = user?.subscription?.pending_plan || "";
  const pendingDate = planDate(user?.subscription?.pending_effective_at);
  const accessEndDate = planDate(user?.subscription?.expires_at);
  const isDowngrade = (code) => (PLAN_RANK[code] || 0) < (PLAN_RANK[currentPlan] || 0);
  const planName = (code) => plans.find((plan) => plan.code === code)?.name || codeLabel("plans", code);
  const currentPlanInfo = useMemo(
    () => plans.find((plan) => plan.code === currentPlan),
    [plans, currentPlan],
  );
  const promotionActive = Boolean(billing?.promotion?.active);

  useEffect(() => {
    let active = true;
    getPlans().then((availablePlans) => { if (active) setPlans(availablePlans); })
      .catch((err) => { if (active) setError(err.message || tx("No se pudieron cargar los planes.", "We couldn’t load the plans.")); })
      .finally(() => { if (active) setLoading(false); });
    getBillingCatalog().then((catalog) => { if (active) setBilling(catalog); })
      .catch(() => { if (active) setBillingError(pricesUnavailable()); });
    return () => { active = false; };
  }, []);

  const retryBilling = () => {
    setBillingError("");
    getBillingCatalog().then(setBilling)
      .catch(() => setBillingError(pricesUnavailable()));
  };


  const openPlanDialog = (planCode) => {
    if (planCode === currentPlan || planCode === pendingPlan) return;
    if (planCode !== "free" && !isDowngrade(planCode) && !billing) { setError(tx("Confirmá los precios antes de elegir un plan de pago.", "Confirm prices before choosing a paid plan.")); return; }
    setConfirming(planCode);
    setMessage("");
    setError("");
  };

  const changePlan = async () => {
    const planCode = confirming;
    if (!planCode || (planCode === currentPlan && !pendingPlan)) return;
    if (planCode !== "free" && planCode !== currentPlan && !isDowngrade(planCode) && !promotionActive) return;
    setChanging(planCode);
    setError("");
    setMessage("");
    try {
      const response = await selectPlan(planCode, false);
      const activeProfile = await confirmedPlanProfile(response, planCode, getMe);
      identifyTelemetryUser(activeProfile);
      const change = response?.status === "downgrade_scheduled" ? "scheduled" : response?.status === "plan_kept" ? "kept" : "immediate";
      trackEvent("plan_selected", { plan: planCode, change });
      if (!["downgrade_scheduled", "plan_kept"].includes(response?.status)) {
        trackEvent("plan_access_granted", { plan: planCode, access_type: planCode === "free" ? "free" : "promotion" });
      }
      onUserChange?.(activeProfile);
      setConfirming("");
      const newPlan = activeProfile.subscription.plan;
      if (response?.status === "downgrade_scheduled") {
        const when = planDate(activeProfile.subscription.pending_effective_at);
        setMessage(tx(`Listo. Seguís con ${planName(newPlan)} hasta el ${when}; después cambia tu plan.`, `Done. You keep ${planName(newPlan)} until ${when}; then your plan changes.`));
      } else if (response?.status === "plan_kept") {
        setMessage(tx(`Seguís con ${planName(newPlan)}. Cancelamos el cambio programado.`, `You keep ${planName(newPlan)}. We canceled the scheduled change.`));
      } else {
        setMessage(tx(`Plan cambiado a ${newPlan === "free" ? "Gratis" : newPlan.toUpperCase()}.`, `Plan changed to ${newPlan === "free" ? "Free" : newPlan.toUpperCase()}.`));
      }
    } catch (err) {
      setError(err.message || tx("No se pudo cambiar el plan.", "We couldn’t change the plan."));
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
          <strong>{user?.display_name || tx("Usuario", "User")}</strong>
          <small>{user?.email}</small>
        </div>
        <span className="role-pill">{roleLabel(user?.role)}</span>
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
          <strong>{currentPlanInfo?.name || codeLabel("plans", currentPlan)}</strong>
          <span>{currentPlanInfo?.tagline || tx("Plan personal DINCR", "DINCR personal plan")}</span>
        </div>
        <span className="plan-status-pill">{tx("Actual","Current")}</span>
      </article>
      {pendingPlan && (
        <p className="plan-payment-notice" role="status">
          <CheckCircle2 size={19}/>
          <span>
            {tx(`Tu plan ${planName(currentPlan)} sigue activo hasta el ${pendingDate}.`, `Your ${planName(currentPlan)} plan stays active until ${pendingDate}.`)}
            {" "}
            {user?.subscription?.pending_requires_payment
              ? tx(`Después pasarás a ${planName(pendingPlan)} si tenés una compra activa; si no, a Gratis.`, `Then you’ll move to ${planName(pendingPlan)} if you have an active purchase; otherwise to Free.`)
              : tx(`Después pasarás a ${planName(pendingPlan)}.`, `Then you’ll move to ${planName(pendingPlan)}.`)}
            {" "}
            <button type="button" className="change-plan-button" disabled={Boolean(changing)} onClick={() => setConfirming(currentPlan)}>
              {tx(`Mantener ${planName(currentPlan)}`, `Keep ${planName(currentPlan)}`)}
            </button>
          </span>
        </p>
      )}

      <div className="section-heading compact plan-change-heading">
        <div>
          <p className="eyebrow">{tx("Planes", "Plans")}</p>
          <h2>{tx("Cambiar de plan","Change plan")}</h2>
          <span>{!billing ? tx("Estamos confirmando los precios de Basic y VIP.", "We’re confirming Basic and VIP prices.") : promotionActive ? tx("Basic y VIP están gratis hasta el 31 de diciembre de 2026. No habrá cobro automático.", "Basic and VIP are free until December 31, 2026. There will be no automatic charge.") : tx("Las compras de Basic y VIP desde Google Play y App Store estarán disponibles más adelante.", "Basic and VIP purchases through Google Play and the App Store will be available later.")}</span>
        </div>
      </div>

      {loading ? (
        <div className="mobile-panel"><p>{tx("Cargando planes...","Loading plans...")}</p></div>
      ) : (
        <div className="settings-plan-list">
          {plans.map((plan) => {
            const Icon = icons[plan.code] || WalletCards;
            const isCurrent = plan.code === currentPlan;
            const isPending = plan.code === pendingPlan;
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
                ) : isPending ? (
                  <span className="selected-plan-label">{tx(`Desde el ${pendingDate}`, `From ${pendingDate}`)}</span>
                ) : (
                  <button
                    type="button"
                    className="change-plan-button"
                    disabled={Boolean(changing) || (plan.code !== "free" && !isDowngrade(plan.code) && (!billing || !promotionActive))}
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

      {billingError && <p className="onboarding-error" role="status">{billingError} <button type="button" onClick={retryBilling}>{tx("Reintentar", "Retry")}</button></p>}

      {message && <p className="success-banner">{message}</p>}
      {!confirming && error && <p className="onboarding-error">{error}</p>}

      {confirming && (confirming !== currentPlan || pendingPlan) && (() => {
        const selected = plans.find((plan) => plan.code === confirming);
        const SelectedIcon = icons[confirming] || WalletCards;
        return <div className="plan-dialog-backdrop" role="presentation" onMouseDown={(event)=>{if(event.target===event.currentTarget&&!changing)setConfirming("");}}>
          <section className={`plan-dialog plan-${confirming}`} role="dialog" aria-modal="true" aria-labelledby="plan-dialog-title">
            <button className="plan-dialog-close" type="button" aria-label={tx("Cerrar","Close")} disabled={Boolean(changing)} onClick={()=>setConfirming("")}><X size={20}/></button>
            <div className="plan-dialog-icon"><SelectedIcon size={28}/></div>
            <p className="eyebrow">{tx("Confirmar cambio","Confirm change")}</p>
            <h2 id="plan-dialog-title">{confirming === currentPlan ? tx("Mantener", "Keep") : tx("Cambiar a", "Switch to")} {selected?.name || confirming.toUpperCase()}</h2>
            <p>{selected?.tagline || tx("Tu nuevo plan DINCR", "Your new DINCR plan")}</p>
            <PlanChangeNotice
              confirming={confirming}
              currentPlan={currentPlan}
              pendingPlan={pendingPlan}
              accessEndDate={accessEndDate}
              planName={planName}
              isDowngrade={isDowngrade}
            />
            {confirming !== "free" && confirming !== currentPlan && !isDowngrade(confirming) && <div className="plan-payment-notice"><CheckCircle2 size={19}/><span>{tx(`Este plan estará gratis hasta el 31 de diciembre de 2026. Desde enero su precio previsto será ${confirming === "basic" ? "₡2.990" : "₡4.990"}/mes, sin cobro automático.`, `This plan will be free until December 31, 2026. From January its planned price will be ${confirming === "basic" ? "₡2,990" : "₡4,990"}/month, with no automatic charge.`)}</span></div>}
            {error && <div className="plan-dialog-error"><AlertTriangle size={18}/><span>{error}</span></div>}
            <div className="plan-dialog-actions"><button type="button" className="plan-dialog-cancel" disabled={Boolean(changing)} onClick={()=>setConfirming("")}>{tx("Cancelar","Cancel")}</button><button type="button" className="plan-dialog-confirm" disabled={Boolean(changing)} onClick={changePlan}>{changing ? tx("Procesando...","Processing...") : `${tx("Confirmar","Confirm")} ${selected?.name || confirming.toUpperCase()}`}</button></div>
          </section>
        </div>;
      })()}

      <AccountActions onLogout={onLogout} variant={currentPlan} />
    </section>
  );
}
