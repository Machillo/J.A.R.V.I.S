import { Check, Crown, LogOut, Sparkles, WalletCards } from "lucide-react";
import { useEffect, useState } from "react";
import { getPlans, selectPlan } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";

const icons = { free: WalletCards, basic: Sparkles, vip: Crown };

export default function PlanSelection({ onSelected }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getPlans().then(setPlans).catch((err) => setError(err.message)).finally(() => setLoading(false));
  }, []);

  const choose = async (code) => {
    setSaving(code); setError("");
    try { const response = await selectPlan(code); onSelected(response.profile); }
    catch (err) { setError(err.message || "No se pudo seleccionar el plan."); }
    finally { setSaving(""); }
  };

  return <main className="onboarding-shell"><section className="onboarding-card plan-selection-card">
    <header className="onboarding-topbar"><div><strong>J.A.R.V.I.S.</strong><small>Elegí cómo querés empezar</small></div><button className="onboarding-logout" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> Cerrar sesión</button></header>
    <div className="onboarding-heading"><p>Planes personales</p><h1>Elegí tu JARVIS</h1><span>Podrás cambiar de plan más adelante. Los cobros todavía no están habilitados durante esta etapa de desarrollo.</span></div>
    {loading ? <p>Preparando planes...</p> : <div className="plan-grid">{plans.map((plan) => { const Icon=icons[plan.code] || WalletCards; return <article className={`plan-card plan-${plan.code}`} key={plan.code}><Icon size={28}/><h2>{plan.name}</h2><p>{plan.tagline}</p><ul>{plan.features.map((feature)=><li key={feature}><Check size={16}/>{feature}</li>)}</ul><button className="primary" disabled={Boolean(saving)} onClick={()=>choose(plan.code)}>{saving===plan.code ? "Seleccionando..." : `Elegir ${plan.name}`}</button></article>; })}</div>}
    {error && <p className="onboarding-error">{error}</p>}
  </section></main>;
}
