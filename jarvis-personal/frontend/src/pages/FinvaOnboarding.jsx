import { useEffect, useRef, useState } from "react";
import { Check, CheckCircle2, ChevronDown, ChevronUp, Crown, LogOut, Sparkles, WalletCards } from "lucide-react";
import { getBillingCatalog, getMe, getPlans, selectPlan } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";
import { markFinvaWelcomeSeen, shouldShowFinvaWelcome } from "../lib/firstRunExperience";
import FinvaWelcomeStory from "./FinvaWelcomeStory";
import { confirmedPlanProfile } from "../lib/planSelection";
import { identifyTelemetryUser, trackEvent } from "../lib/telemetry";
import { localeTag, tx } from "../lib/locale";

const iconMap = { free: WalletCards, basic: Sparkles, vip: Crown };
const billingUnavailable = () => tx("No pudimos confirmar los precios y la promoción. Reintentá para elegir Basic o VIP.", "We couldn’t confirm prices and the promotion. Retry to choose Basic or VIP.");
const formatColones = (amount) => `₡${Number(amount || 0).toLocaleString(localeTag())}`;

export default function FinvaOnboarding({ user, onComplete }) {
  const completedRef = useRef(false);
  const analyticsStartedRef = useRef(false);
  const [profile, setProfile] = useState(user);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [expandedPlan, setExpandedPlan] = useState("");
  const [billing, setBilling] = useState(null);
  const [billingError, setBillingError] = useState("");
  const [showWelcome, setShowWelcome] = useState(() => shouldShowFinvaWelcome(user?.id));

  useEffect(() => {
    let active = true;
    getPlans().then((rows) => { if (active) setPlans(rows); })
      .catch((e) => { if (active) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    getMe().then((fresh) => {
      if (active && fresh?.plan_selected) setProfile(fresh);
    }).catch(() => {});
    getBillingCatalog().then((catalog) => {
      if (!active) return;
      setBilling(catalog);
    }).catch(() => { if (active) setBillingError(billingUnavailable()); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (analyticsStartedRef.current || user?.legal?.required !== false) return;
    analyticsStartedRef.current = true;
    identifyTelemetryUser(user);
    trackEvent("onboarding_started");
  }, [user]);

  const retryBilling = () => {
    setBillingError("");
    getBillingCatalog().then((catalog) => {
      setBilling(catalog);
    })
      .catch(() => setBillingError(billingUnavailable()));
  };

  const retryPlans = () => {
    setLoading(true); setError("");
    getPlans().then(setPlans)
      .catch((e) => setError(e.message || tx("No pudimos cargar los planes.", "We couldn’t load the plans.")))
      .finally(() => setLoading(false));
  };

  const promotionActive = Boolean(billing?.promotion?.active);

  useEffect(() => {
    if (profile?.plan_selected && !completedRef.current) {
      completedRef.current = true;
      onComplete(profile);
    }
  }, [profile, onComplete]);

  const choosePlan = async (code) => {
    if (code !== "free" && !billing) {
      setBillingError(tx("Esperá a que podamos confirmar los precios antes de elegir este plan.", "Wait until we can confirm prices before choosing this plan."));
      return;
    }
    if (code !== "free" && !promotionActive) return;
    setSaving(true); setError("");
    try {
      const result = await selectPlan(code, false);
      // The plan mutation already returns the updated identity. A second
      // request here could fail after activation and strand the onboarding UI.
      const activeProfile = await confirmedPlanProfile(result, code, getMe);
      identifyTelemetryUser(activeProfile);
      trackEvent("plan_selected", { plan: code });
      trackEvent("plan_access_granted", { plan: code, access_type: code === "free" ? "free" : "promotion" });
      trackEvent("onboarding_completed");
      setProfile(activeProfile);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const finishWelcome = () => {
    markFinvaWelcomeSeen(user?.id);
    setShowWelcome(false);
  };

  if (!profile?.plan_selected && showWelcome) {
    return <FinvaWelcomeStory user={profile} onFinish={finishWelcome} />;
  }

  if (!profile?.plan_selected) return <main className="unified-onboarding-shell">
    <section className="unified-onboarding-card unified-plan-stage">
      <div className="unified-onboarding-top">
        <div><strong>DINCR</strong><small>{tx("Elegí tu plan personal", "Choose your personal plan")}</small></div>
        <button type="button" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> {tx("Salir", "Sign out")}</button>
      </div>
      <div className="unified-onboarding-intro">
        <span className="unified-eyebrow">{tx("BIENVENIDO", "WELCOME")}</span>
        <h1>{tx("Tu espacio financiero empieza acá", "Your financial space starts here")}</h1>
        <p>{tx("Cada cuenta recibe su propio espacio aislado. Podés empezar gratis y cambiar de plan cuando corresponda.", "Each account gets its own private space. You can start for free and change plans whenever it makes sense.")}</p>
      </div>
      {loading ? <div className="unified-loading"><div className="unified-spinner"/><span>{tx("Preparando tus planes...", "Preparing your plans...")}</span></div> : <div className="unified-plan-list">{plans.map((item) => {
        const Icon = iconMap[item.code] || WalletCards;
        const expanded = expandedPlan === item.code;
        return <article key={item.code} className={`unified-plan-card ${item.code} ${expanded ? "is-expanded" : ""}`}>
          <button type="button" className="unified-plan-summary" aria-expanded={expanded} onClick={() => { setExpandedPlan(expanded ? "" : item.code); setError(""); }}>
            <span className="unified-plan-icon"><Icon size={22}/></span>
            <span className="unified-plan-copy"><span>{item.code === "free" ? tx("EMPEZÁ HOY", "START TODAY") : item.code === "basic" ? tx("MÁS CONTROL", "MORE CONTROL") : tx("EXPERIENCIA COMPLETA", "FULL EXPERIENCE")}</span><strong>{item.name}</strong><small>{item.tagline}</small></span>
            <span className="unified-plan-price">{item.code === "free" ? "₡0" : !billing ? "—" : promotionActive ? "₡0" : formatColones(item.regular_price_crc)}<small>{item.code === "free" || !billing ? "" : promotionActive ? tx(" hasta 31 dic", " until Dec 31") : tx("/mes", "/mo")}</small></span>
            {expanded ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}
          </button>
          {expanded && <div className="unified-plan-details">
            <ul>{item.features.map(f => <li key={f}><Check size={16}/><span>{f}</span></li>)}</ul>
            {item.code !== "free" && billing && <div className="unified-payment-preview"><CheckCircle2 size={18}/><span>{promotionActive ? tx(`Acceso gratuito hasta el 31 de diciembre de 2026. Después el precio previsto es ${formatColones(item.regular_price_crc)}/mes, sin cobro automático.`, `Free access until December 31, 2026. After that, the expected price is ${formatColones(item.regular_price_crc)}/month, with no automatic charge.`) : tx("Las compras desde Google Play y App Store estarán disponibles más adelante. Mientras tanto podés usar Gratis.", "Purchases through Google Play and the App Store will be available later. Meanwhile, you can use Free.")}</span></div>}
            <button className="unified-plan-button" disabled={saving || (item.code !== "free" && (!billing || !promotionActive))} onClick={() => choosePlan(item.code)}>{saving ? tx("Preparando...", "Preparing...") : item.code === "free" ? tx("Empezar gratis", "Start for free") : !billing ? tx("Verificando precio...", "Checking price...") : promotionActive ? tx(`Activar ${item.name} gratis`, `Activate ${item.name} for free`) : tx("Próximamente en las tiendas", "Coming soon to the stores")}</button>
          </div>}
        </article>;
      })}</div>}
      {error && <div className="unified-onboarding-error" role="alert">{error} {!plans.length && <button type="button" onClick={retryPlans}>{tx("Reintentar", "Retry")}</button>}</div>}
      {billingError && <div role="status" className="unified-onboarding-error">{billingError} <button type="button" onClick={retryBilling}>{tx("Reintentar", "Retry")}</button></div>}
    </section>
  </main>;

  return <main className="unified-onboarding-shell">
    <section className="unified-onboarding-card unified-loading">
      <div className="unified-spinner"/>
      <span>{tx("Abriendo DINCR…", "Opening DINCR…")}</span>
    </section>
  </main>;
}
