import { useEffect, useRef, useState } from "react";
import { Check, CheckCircle2, ChevronDown, ChevronUp, Crown, LogOut, Sparkles, WalletCards } from "lucide-react";
import { getBillingCatalog, getMe, getPlans, selectPlan } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";
import { markFinvaWelcomeSeen, shouldShowFinvaWelcome } from "../lib/firstRunExperience";
import FinvaWelcomeStory from "./FinvaWelcomeStory";
import { confirmedPlanProfile } from "../lib/planSelection";
import { identifyTelemetryUser, trackEvent } from "../lib/telemetry";

const iconMap = { free: WalletCards, basic: Sparkles, vip: Crown };

export default function FinvaOnboarding({ user, onComplete }) {
  const completedRef = useRef(false);
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
    }).catch(() => { if (active) setBillingError("No pudimos confirmar los precios y la promoción. Reintentá para elegir Basic o VIP."); });
    return () => { active = false; };
  }, []);

  const retryBilling = () => {
    setBillingError("");
    getBillingCatalog().then((catalog) => {
      setBilling(catalog);
    })
      .catch(() => setBillingError("No pudimos confirmar los precios y la promoción. Reintentá para elegir Basic o VIP."));
  };

  const retryPlans = () => {
    setLoading(true); setError("");
    getPlans().then(setPlans)
      .catch((e) => setError(e.message || "No pudimos cargar los planes."))
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
      setBillingError("Esperá a que podamos confirmar los precios antes de elegir este plan.");
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
      trackEvent("plan_access_granted", { plan: code, access_type: code === "free" ? "free" : "promotion" });
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
        <div><strong>DINCR</strong><small>Elegí tu plan personal</small></div>
        <button type="button" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> Salir</button>
      </div>
      <div className="unified-onboarding-intro">
        <span className="unified-eyebrow">BIENVENIDO</span>
        <h1>Tu espacio financiero empieza acá</h1>
        <p>Cada cuenta recibe su propio espacio aislado. Podés empezar gratis y cambiar de plan cuando corresponda.</p>
      </div>
      {loading ? <div className="unified-loading"><div className="unified-spinner"/><span>Preparando tus planes...</span></div> : <div className="unified-plan-list">{plans.map((item) => {
        const Icon = iconMap[item.code] || WalletCards;
        const expanded = expandedPlan === item.code;
        return <article key={item.code} className={`unified-plan-card ${item.code} ${expanded ? "is-expanded" : ""}`}>
          <button type="button" className="unified-plan-summary" aria-expanded={expanded} onClick={() => { setExpandedPlan(expanded ? "" : item.code); setError(""); }}>
            <span className="unified-plan-icon"><Icon size={22}/></span>
            <span className="unified-plan-copy"><span>{item.code === "free" ? "EMPEZÁ HOY" : item.code === "basic" ? "MÁS CONTROL" : "EXPERIENCIA COMPLETA"}</span><strong>{item.name}</strong><small>{item.tagline}</small></span>
            <span className="unified-plan-price">{item.code === "free" ? "₡0" : !billing ? "—" : promotionActive ? "₡0" : `₡${Number(item.regular_price_crc || 0).toLocaleString("es-CR")}`}<small>{item.code === "free" || !billing ? "" : promotionActive ? " hasta 31 dic" : "/mes"}</small></span>
            {expanded ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}
          </button>
          {expanded && <div className="unified-plan-details">
            <ul>{item.features.map(f => <li key={f}><Check size={16}/><span>{f}</span></li>)}</ul>
            {item.code !== "free" && billing && <div className="unified-payment-preview"><CheckCircle2 size={18}/><span>{promotionActive ? `Acceso gratuito hasta el 31 de diciembre de 2026. Después el precio previsto es ₡${Number(item.regular_price_crc || 0).toLocaleString("es-CR")}/mes, sin cobro automático.` : "Las compras desde Google Play y App Store estarán disponibles más adelante. Mientras tanto podés usar Gratis."}</span></div>}
            <button className="unified-plan-button" disabled={saving || (item.code !== "free" && (!billing || !promotionActive))} onClick={() => choosePlan(item.code)}>{saving ? "Preparando..." : item.code === "free" ? "Empezar gratis" : !billing ? "Verificando precio..." : promotionActive ? `Activar ${item.name} gratis` : "Próximamente en las tiendas"}</button>
          </div>}
        </article>;
      })}</div>}
      {error && <div className="unified-onboarding-error" role="alert">{error} {!plans.length && <button type="button" onClick={retryPlans}>Reintentar</button>}</div>}
      {billingError && <div role="status" className="unified-onboarding-error">{billingError} <button type="button" onClick={retryBilling}>Reintentar</button></div>}
    </section>
  </main>;

  return <main className="unified-onboarding-shell">
    <section className="unified-onboarding-card unified-loading">
      <div className="unified-spinner"/>
      <span>Abriendo DINCR…</span>
    </section>
  </main>;
}
