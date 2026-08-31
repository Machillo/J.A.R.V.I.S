import { useEffect, useState } from "react";
import { Check, Crown, LogOut, Sparkles, WalletCards } from "lucide-react";
import { completeOnboarding, getPlans, selectPlan } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";

const iconMap = { free: WalletCards, basic: Sparkles, vip: Crown };
const label = (p) => p === "free" ? "Gratis" : p?.toUpperCase();

export default function UnifiedOnboarding({ user, onComplete }) {
  const [profile, setProfile] = useState(user);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    income_type: "fixed", fixed_monthly_salary: "", hourly_rate: "", hours_per_day: "8",
    work_days_per_week: "5", pay_frequency: "monthly", payday_note: "",
    essential_monthly_expenses: "", liquid_savings: "", emergency_fund_target: "",
    strategy_preference: "balanced", discretionary_monthly_minimum: "",
  });

  useEffect(() => { getPlans().then(setPlans).catch(e => setError(e.message)).finally(() => setLoading(false)); }, []);
  const plan = profile?.subscription?.plan || "free";
  const numberOrNull = (v) => v === "" ? null : Number(v);

  const choosePlan = async (code) => {
    setSaving(true); setError("");
    try { const result = await selectPlan(code); setProfile(result.profile); }
    catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const submit = async (e) => {
    e.preventDefault(); setSaving(true); setError("");
    try {
      const result = await completeOnboarding({
        income_type: form.income_type,
        fixed_monthly_salary: form.income_type === "fixed" ? numberOrNull(form.fixed_monthly_salary) : null,
        hourly_rate: form.income_type === "hourly" ? numberOrNull(form.hourly_rate) : null,
        hours_per_day: form.income_type === "hourly" ? numberOrNull(form.hours_per_day) : null,
        work_days_per_week: Number(form.work_days_per_week), pay_frequency: form.pay_frequency,
        payday_note: form.payday_note || null,
        essential_monthly_expenses: numberOrNull(form.essential_monthly_expenses),
        liquid_savings: numberOrNull(form.liquid_savings), emergency_fund_target: numberOrNull(form.emergency_fund_target),
        strategy_preference: plan === "vip" ? form.strategy_preference : null,
        discretionary_monthly_minimum: numberOrNull(form.discretionary_monthly_minimum),
      });
      onComplete(result.profile);
    } catch (e2) { setError(e2.message); }
    finally { setSaving(false); }
  };

  if (!profile?.plan_selected) return <main className="unified-onboarding-shell"><section className="unified-onboarding-card">
    <div className="unified-onboarding-top"><div><strong>J.A.R.V.I.S.</strong><small>Elegí tu plan personal</small></div><button onClick={() => supabase.auth.signOut()}><LogOut size={17}/> Salir</button></div>
    <h1>Tu espacio financiero empieza acá</h1><p>Cada cuenta recibe su propio account y workspace aislado.</p>
    {loading ? <p>Preparando planes...</p> : <div className="unified-plan-grid">{plans.map((item) => { const Icon=iconMap[item.code]||WalletCards; return <article key={item.code}><Icon size={28}/><h2>{item.name}</h2><p>{item.tagline}</p><ul>{item.features.map(f=><li key={f}><Check size={15}/>{f}</li>)}</ul><button disabled={saving} onClick={()=>choosePlan(item.code)}>Elegir {item.name}</button></article>; })}</div>}
    {error && <p className="unified-onboarding-error">{error}</p>}
  </section></main>;

  return <main className="unified-onboarding-shell"><form className="unified-onboarding-card" onSubmit={submit}>
    <div className="unified-onboarding-top"><div><strong>J.A.R.V.I.S.</strong><small>Onboarding {label(plan)}</small></div><button type="button" onClick={() => supabase.auth.signOut()}><LogOut size={17}/> Salir</button></div>
    <h1>Contame cómo funcionan tus finanzas</h1><p>Solo pedimos lo necesario para tu nivel. Después podés afinar todo dentro de JARVIS.</p>
    <div className="unified-form-grid">
      <label>Tipo de ingreso<select value={form.income_type} onChange={e=>setForm({...form,income_type:e.target.value})}><option value="fixed">Salario fijo</option><option value="hourly">Por hora</option></select></label>
      {form.income_type === "fixed" ? <label>Salario mensual<input required type="number" min="1" value={form.fixed_monthly_salary} onChange={e=>setForm({...form,fixed_monthly_salary:e.target.value})}/></label> : <><label>Tarifa por hora<input required type="number" min="1" value={form.hourly_rate} onChange={e=>setForm({...form,hourly_rate:e.target.value})}/></label><label>Horas por día<input required type="number" min="0.1" max="24" value={form.hours_per_day} onChange={e=>setForm({...form,hours_per_day:e.target.value})}/></label></>}
      <label>Días por semana<input required type="number" min="1" max="7" value={form.work_days_per_week} onChange={e=>setForm({...form,work_days_per_week:e.target.value})}/></label>
      <label>Frecuencia de pago<select value={form.pay_frequency} onChange={e=>setForm({...form,pay_frequency:e.target.value})}><option value="weekly">Semanal</option><option value="biweekly">Quincenal</option><option value="monthly">Mensual</option></select></label>
      <label>Días de pago<input value={form.payday_note} placeholder="Ej. cada jueves" onChange={e=>setForm({...form,payday_note:e.target.value})}/></label>
      {plan !== "free" && <><label>Gastos esenciales mensuales<input required type="number" min="0" value={form.essential_monthly_expenses} onChange={e=>setForm({...form,essential_monthly_expenses:e.target.value})}/></label><label>Ahorro líquido<input type="number" min="0" value={form.liquid_savings} onChange={e=>setForm({...form,liquid_savings:e.target.value})}/></label></>}
      {plan === "vip" && <><label>Meta fondo emergencia<input type="number" min="0" value={form.emergency_fund_target} onChange={e=>setForm({...form,emergency_fund_target:e.target.value})}/></label><label>Prioridad<select value={form.strategy_preference} onChange={e=>setForm({...form,strategy_preference:e.target.value})}><option value="balanced">Equilibrado</option><option value="debt">Salir de deudas</option><option value="emergency">Seguridad</option><option value="goals">Metas</option></select></label><label>Mínimo mensual para vos<input type="number" min="0" value={form.discretionary_monthly_minimum} onChange={e=>setForm({...form,discretionary_monthly_minimum:e.target.value})}/></label></>}
    </div>
    <button className="unified-primary" disabled={saving}>{saving ? "Guardando..." : `Activar ${label(plan)}`}</button>
    {error && <p className="unified-onboarding-error">{error}</p>}
  </form></main>;
}
