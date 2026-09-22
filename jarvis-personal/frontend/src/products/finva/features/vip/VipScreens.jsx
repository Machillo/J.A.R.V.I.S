import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ChevronRight, Mail, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { deviceLanguage, localeTag } from "../../../../lib/locale";
import AccountActions from "../../components/AccountActions";
import {
  captureVipLifecycleSnapshot,
  getBudget,
  getFinancialSituation,
  getVipMonthlyReview,
  getVipProactiveAdvisor,
  getVipAguinaldo,
  getVipCommandCenter,
  getVipGmailStatus,
  simulateStrategyVip,
  syncVipGmail,
  updateFinancialSituation,
} from "../../../../users/services/jarvisApi";

const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;
const money = (value) => new Intl.NumberFormat(localeTag(language), {
  style: "currency", currency: "CRC", maximumFractionDigits: 0,
}).format(Number(value) || 0);
const percent = (value) => `${Math.round(Number(value) || 0)}%`;
const strategyText = (value = "") => {
  if (language === "es") return value;
  const exact = {
    "Eliminar déficit":"Eliminate deficit",
    "Completar reserva":"Complete emergency fund",
    "Invertir":"Invest",
    "Esperar para invertir":"Wait before investing",
    "Sin flujo positivo no hay dinero seguro para deuda, metas o inversión.":"Without positive cash flow, there is no safe money for debt, goals, or investing.",
    "Protege tus obligaciones ante un imprevisto.":"It protects your obligations against the unexpected.",
    "Es el uso de menor costo financiero según saldo y tasa conocidos.":"It is the lowest-cost use based on known balances and rates.",
    "Alinea el aporte con fecha y prioridad.":"It aligns the contribution with its date and priority.",
    "Primero deben estar protegidos el flujo, la reserva y la deuda cara.":"Cash flow, reserves, and expensive debt must be protected first.",
  };
  if (exact[value]) return exact[value];
  if (value.startsWith("Abonar a ")) return `Pay extra toward ${value.slice(9)}`;
  if (value.startsWith("Financiar ")) return `Fund ${value.slice(10)}`;
  return value;
};

function VipHeader({ title, user, onNavigate }) {
  const initial = (user?.display_name || user?.email || "U").slice(0, 1).toUpperCase();
  return <header className="vip-screen-header">
    <div><small>DINCR · VIP</small><h1>{title}</h1></div>
    <button type="button" onClick={() => onNavigate?.("settings")} aria-label={tx("Abrir ajustes", "Open settings")}>{initial}</button>
  </header>;
}

function Focus({ eyebrow, title, caption, tone = "violet", children }) {
  return <article className={`vip-focus vip-tone-${tone}`}>
    {eyebrow && <small>{eyebrow}</small>}
    {title && <strong>{title}</strong>}
    {caption && <p>{caption}</p>}
    {children}
  </article>;
}

function Card({ title, tone = "", children, className = "" }) {
  return <article className={`vip-card ${tone ? `vip-card--${tone}` : ""} ${className}`.trim()}>
    {title && <h2>{title}</h2>}{children}
  </article>;
}

function DataRow({ label, value, tone = "" }) {
  return <div className="vip-data-row"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}

function PrimaryButton({ children, ...props }) {
  return <button type="button" className="vip-primary" {...props}>{children}</button>;
}

function LoadingScreen() {
  return <section className="vip-screen vip-loading" aria-live="polite">
    <div className="vip-loading-header"/><div className="vip-loading-focus"/><div className="vip-loading-card"/><div className="vip-loading-card"/>
    <span>{tx("Construyendo tu estrategia VIP…", "Building your VIP strategy…")}</span>
  </section>;
}

export default function VipScreens({ view = "dashboard", onNavigate, onLogout, user }) {
  const [data, setData] = useState(null);
  const [profile, setProfile] = useState(null);
  const [budget, setBudget] = useState(null);
  const [error, setError] = useState("");
  const load = () => {
    setError("");
    Promise.all([getVipCommandCenter(), getFinancialSituation(), getBudget()])
      .then(([vip, situation, budgetData]) => {
        setData(vip); setProfile(situation?.financial_profile || {}); setBudget(budgetData || {});
      })
      .catch(() => setError(tx("No pudimos cargar tu estrategia. Intentá nuevamente.", "We couldn't load your strategy. Please try again.")));
  };
  useEffect(load, []);
  useEffect(() => {
    if (view === "dashboard") captureVipLifecycleSnapshot().catch(() => {});
  }, [view]);
  if (!data || !profile) {
    if (error) return <section className="vip-screen"><Card tone="danger"><h2>{error}</h2><PrimaryButton onClick={load}>{tx("Reintentar", "Try again")}</PrimaryButton></Card></section>;
    return <LoadingScreen/>;
  }
  const props = { data, profile, budget, onNavigate, onLogout, user, reload: load };
  const needsActivation = !profile.strategy_preference || profile.emergency_fund_target == null || profile.discretionary_monthly_minimum == null;
  if (needsActivation && view === "dashboard") return <VipActivation {...props}/>;
  const screens = {
    dashboard: VipDashboard, strategy: VipStrategy, recommendation: VipRecommendation,
    projections: VipProjections, "projection-detail": VipProjectionDetail,
    scenarios: VipScenarios, goal: VipSmartGoal, emergency: VipEmergency,
    reality: VipReality, "monthly-review": VipMonthlyReview, today: VipToday, more: VipMore,
    aguinaldo: VipAguinaldo, preferences: VipPreferences,
  };
  const Screen = screens[view] || VipDashboard;
  return <Screen {...props}/>;
}

function VipActivation({ profile, user, onNavigate, reload }) {
  const [form, setForm] = useState({
    ...profile,
    emergency_fund_target: profile.emergency_fund_target ?? 0,
    strategy_preference: profile.strategy_preference || "balanced",
    discretionary_monthly_minimum: profile.discretionary_monthly_minimum ?? 0,
  });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try {
      await updateFinancialSituation({
        ...form,
        emergency_fund_target: Number(form.emergency_fund_target) || 0,
        discretionary_monthly_minimum: Number(form.discretionary_monthly_minimum) || 0,
      });
      await reload(); onNavigate?.("overview");
    } finally { setSaving(false); }
  };
  return <section className="vip-screen">
    <VipHeader title={tx("Completemos VIP", "Let's complete VIP")} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={tx("TODO FREE + BASIC SE CONSERVA", "EVERYTHING IN FREE + BASIC STAYS")} caption={tx("Solo necesitamos 3 decisiones para personalizar tu estrategia.", "We only need 3 decisions to personalize your strategy.")}/>
    <label className="vip-field"><span>{tx("Fondo de emergencia objetivo", "Emergency fund target")}</span><input type="number" min="0" value={form.emergency_fund_target} onChange={(e) => setForm({...form, emergency_fund_target:e.target.value})}/></label>
    <label className="vip-field"><span>{tx("Prioridad estratégica", "Strategic priority")}</span><select value={form.strategy_preference} onChange={(e) => setForm({...form, strategy_preference:e.target.value})}><option value="balanced">{tx("Equilibrado", "Balanced")}</option><option value="debt">{tx("Deuda", "Debt")}</option><option value="emergency">{tx("Emergencia", "Emergency")}</option><option value="goals">{tx("Metas", "Goals")}</option></select></label>
    <label className="vip-field"><span>{tx("Dinero mínimo para tus gustos", "Minimum personal spending")}</span><input type="number" min="0" value={form.discretionary_monthly_minimum} onChange={(e) => setForm({...form, discretionary_monthly_minimum:e.target.value})}/></label>
    <Card tone="gold"><h2>{tx("Tu estrategia será ajustable", "Your strategy will be adjustable")}</h2><p>{tx("Podés cambiar estas preferencias cuando tu vida financiera cambie.", "You can change these preferences when your financial life changes.")}</p></Card>
    <PrimaryButton disabled={saving} onClick={save}>{saving ? tx("Activando…", "Activating…") : tx("Activar VIP", "Activate VIP")}</PrimaryButton>
  </section>;
}

function VipDashboard({ data, user, onNavigate }) {
  const roadmap = data.roadmap || [];
  const projection = data.projections?.find((item) => item.months === 6) || data.projections?.[0];
  const [proactive, setProactive] = useState(null);
  useEffect(() => { getVipProactiveAdvisor().then(setProactive).catch(() => {}); }, []);
  const leadAlert = proactive?.alerts?.[0];
  return <section className="vip-screen">
    <VipHeader title={tx("Tu estrategia hoy", "Your strategy today")} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={tx("DISPONIBLE ESTRATÉGICO", "STRATEGIC AVAILABLE")} title={money(data.safe_to_spend?.amount)} caption={tx(`DINCR encontró ${Math.min(roadmap.length, 3)} acciones para este mes`, `DINCR found ${Math.min(roadmap.length, 3)} actions for this month`)}/>
    <Card title={tx("Prioridad recomendada", "Recommended priority")}>
      {roadmap.slice(0, 3).map((item, index) => <DataRow key={`${item.order}-${item.title}`} label={strategyText(item.title)} value={item.amount ? `+ ${money(item.amount)}` : "—"} tone={["coral", "mint", "gold"][index]}/>) }
      <p>{tx("Mantiene tus gastos esenciales y mínimo personal protegidos.", "Your essential expenses and personal minimum remain protected.")}</p>
    </Card>
    <Card title={tx("Si seguís este plan", "If you follow this plan")} tone="violet">
      <DataRow label={tx("Patrimonio estimado · 6 meses", "Estimated net worth · 6 months")} value={projection ? money(projection.net_worth) : "—"}/>
      <DataRow label={tx("Deuda estimada", "Estimated debt")} value={projection ? money(projection.debt) : "—"} tone="mint"/>
    </Card>
    <button className="vip-link-card" type="button" onClick={() => onNavigate?.("vip-reality")}><span><strong>{tx("Plan vs realidad", "Plan vs reality")}</strong><small>{Number(data.reports?.current?.balance) >= 0 ? tx("Tu mes mantiene un balance positivo.", "Your month remains positive.") : tx("Tu mes necesita un ajuste.", "Your month needs an adjustment.")}</small></span><ArrowRight size={17}/></button>
    <button className="vip-link-card vip-link-card--violet" type="button" onClick={() => onNavigate?.("vip-monthly-review")}><span><strong>{tx("Revisión mensual DINCR", "DINCR monthly review")}</strong><small>{tx("Qué cambió, qué aprendió DINCR y cuál es tu siguiente prioridad.", "What changed, what DINCR learned, and your next priority.")}</small></span><ArrowRight size={17}/></button>
    <button className={`vip-link-card ${leadAlert?.severity === "critical" || leadAlert?.severity === "high" ? "vip-link-card--gold" : "vip-link-card--mint"}`} type="button" onClick={() => onNavigate?.("vip-today")}><span><strong>{leadAlert?.title || tx("DINCR Today", "DINCR Today")}</strong><small>{leadAlert?.explanation || proactive?.message || tx("DINCR está observando cambios relevantes sin generar ruido.", "DINCR is watching for meaningful changes without creating noise.")}</small></span><ArrowRight size={17}/></button>
  </section>;
}

function VipStrategy({ data, user, onNavigate }) {
  return <section className="vip-screen">
    <VipHeader title={tx("Estrategia dinámica", "Dynamic strategy")} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={`${tx("PRIORIDAD", "PRIORITY")} · ${(data.director?.priority || "balanced").toUpperCase()}`} title={tx("Tu dinero tiene un orden.", "Your money has an order.")} caption={tx("DINCR reajusta el plan según lo que realmente ocurre.", "DINCR readjusts the plan based on what actually happens.")}/>
    {(data.roadmap || []).slice(0, 4).map((item, index) => <Card key={`${item.order}-${item.title}`} className="vip-priority-card"><DataRow label={`${index + 1} · ${strategyText(item.title)}`} value={item.amount ? money(item.amount) : "—"} tone={["mint", "violet", "gold", "blue"][index]}/><p>{strategyText(item.why)}</p></Card>)}
    <PrimaryButton onClick={() => onNavigate?.("vip-recommendation")}>{tx("Ver recomendaciones", "View recommendations")}</PrimaryButton>
  </section>;
}

function VipRecommendation({ data, user, onNavigate }) {
  const action = data.roadmap?.find((item) => Number(item.amount) > 0) || data.roadmap?.[0];
  const debt = data.debt_planner?.recommended;
  return <section className="vip-screen">
    <VipHeader title={strategyText(action?.title) || tx("Recomendación", "Recommendation")} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={tx("ACCIÓN RECOMENDADA", "RECOMMENDED ACTION")} title={action?.amount ? money(action.amount) : "—"} caption={tx("Además de tus compromisos mensuales habituales.", "In addition to your regular monthly commitments.")}/>
    <Card title={tx("¿Por qué?", "Why?")} tone="gold"><p>{strategyText(action?.why) || tx("La recomendación usa únicamente tus datos financieros conocidos.", "The recommendation only uses your known financial data.")}</p></Card>
    <Card title={tx("Impacto estimado", "Estimated impact")} tone="violet">
      <DataRow label={tx("Deuda objetivo", "Target debt")} value={debt?.target || "—"}/>
      <DataRow label={tx("Tiempo restante", "Time remaining")} value={debt?.months == null ? "—" : `${debt.months} ${tx("meses", "months")}`} tone="mint"/>
      <DataRow label={tx("Interés estimado", "Estimated interest")} value={debt?.interest == null ? "—" : money(debt.interest)} tone="mint"/>
    </Card>
    <PrimaryButton onClick={() => onNavigate?.("vip-scenarios")}>{tx("Simular antes de hacerlo", "Simulate before doing it")}</PrimaryButton>
  </section>;
}

function ProjectionBars({ rows, descending = false }) {
  const values = rows.map((item) => Math.abs(Number(item.net_worth ?? item.debt) || 0));
  const max = Math.max(...values, 1);
  return <div className="vip-chart">{rows.map((item, index) => <div key={`${item.months}-${index}`}><i style={{height:`${Math.max(((descending ? values[0] - values[index] : values[index]) / max) * 82 + 10, 10)}%`}}/><small>{item.months === 1 ? "30d" : `${item.months}m`}</small></div>)}</div>;
}

function VipProjections({ data, user, onNavigate }) {
  const rows = data.projections || [];
  const first = rows[0] || {}, last = rows[rows.length - 1] || {};
  return <section className="vip-screen">
    <VipHeader title={tx("Proyecciones", "Projections")} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={tx("PRÓXIMOS 6 MESES", "NEXT 6 MONTHS")} title={tx("Así podría evolucionar tu dinero", "How your money could evolve")} caption={tx("Estimación basada en tus datos actuales.", "Estimate based on your current data.")}/>
    <Card title={tx("Patrimonio disponible", "Available net worth")}><ProjectionBars rows={rows}/></Card>
    <Card><DataRow label={tx("Deuda total", "Total debt")} value={`${money(first.debt)} → ${money(last.debt)}`} tone="mint"/></Card>
    <Card><DataRow label={tx("Efectivo", "Cash")} value={`${money(first.cash)} → ${money(last.cash)}`} tone="gold"/></Card>
    <PrimaryButton onClick={() => onNavigate?.("vip-projection-detail")}>{tx("Explorar una proyección", "Explore a projection")}</PrimaryButton>
  </section>;
}

function VipProjectionDetail({ data, user, onNavigate }) {
  const rows = data.projections || [], debt = data.debt_planner?.recommended || {};
  return <section className="vip-screen">
    <VipHeader title={`${debt.target || tx("Deuda", "Debt")} · ${tx("Proyección", "Projection")}`} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={tx("CON EL PLAN ACTUAL", "WITH THE CURRENT PLAN")} title={debt.months == null ? tx("Proyección disponible", "Projection available") : tx(`Deuda estimada en ${debt.months} meses`, `Debt estimated in ${debt.months} months`)} caption={tx("El resultado cambia con tus ingresos, gastos y pagos.", "The result changes with your income, expenses, and payments.")} tone="mint"/>
    <Card title={tx("Saldo proyectado", "Projected balance")}><ProjectionBars rows={rows} descending/></Card>
    <Card title={tx("Resumen", "Summary")} tone="gold"><DataRow label={tx("Saldo actual", "Current balance")} value={money(rows[0]?.debt)}/><DataRow label={tx("Pago mensual objetivo", "Target monthly payment")} value={money(debt.monthly_to_target)} tone="violet"/><DataRow label={tx("Interés estimado", "Estimated interest")} value={debt.interest == null ? "—" : money(debt.interest)} tone="mint"/></Card>
    <PrimaryButton onClick={() => onNavigate?.("vip-scenarios")}>{tx("Crear escenario", "Create scenario")}</PrimaryButton>
  </section>;
}

function VipScenarios({ data, user, onNavigate }) {
  const [mode, setMode] = useState("list");
  const [form, setForm] = useState({ monthly_income_change:0, monthly_expense_change:0, one_time_extra:0 });
  const [result, setResult] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const examples = useMemo(() => {
    const target = data.debt_planner?.recommended?.target || tx("una deuda", "a debt");
    return [
      [tx(`Pago extra a ${target}`, `Extra payment to ${target}`), tx("Ahorro de intereses · termina antes", "Interest savings · finishes sooner"), "violet"],
      [tx("Ahorro más cada mes", "Save more each month"), tx("Completá antes tu fondo de emergencia", "Complete your emergency fund sooner"), "gold"],
      [tx("Reduzco gastos", "I reduce expenses"), tx("Más dinero libre durante 6 meses", "More available money over 6 months"), "mint"],
    ];
  }, [data]);
  const run = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const value = await simulateStrategyVip(Object.fromEntries(Object.entries(form).map(([key, amount]) => [key, Number(amount) || 0])));
      setResult(value); setMode("result");
    } catch { setError(tx("No pudimos calcular el escenario. Intentá nuevamente.", "We couldn't calculate the scenario. Please try again.")); }
    finally { setBusy(false); }
  };
  if (mode === "builder") return <section className="vip-screen"><VipHeader title={tx("Nuevo escenario", "New scenario")} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("SIMULACIÓN", "SIMULATION")} title={tx("Probá una decisión", "Try a decision")} caption={tx("No modificará tu plan real.", "It won't modify your real plan.")}/><form className="vip-form" onSubmit={run}><label className="vip-field"><span>{tx("Ingreso mensual adicional", "Additional monthly income")}</span><input type="number" value={form.monthly_income_change} onChange={(e) => setForm({...form, monthly_income_change:e.target.value})}/></label><label className="vip-field"><span>{tx("Cambio en gastos", "Change in expenses")}</span><input type="number" value={form.monthly_expense_change} onChange={(e) => setForm({...form, monthly_expense_change:e.target.value})}/></label><label className="vip-field"><span>{tx("Dinero único disponible", "One-time money available")}</span><input type="number" min="0" value={form.one_time_extra} onChange={(e) => setForm({...form, one_time_extra:e.target.value})}/></label>{error && <p className="vip-form-error">{error}</p>}<button className="vip-primary" disabled={busy}>{busy ? tx("Calculando…", "Calculating…") : tx("Calcular escenario", "Calculate scenario")}</button></form></section>;
  if (mode === "result" && result) return <section className="vip-screen"><VipHeader title={tx("Comparación", "Comparison")} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("ESCENARIO VIP", "VIP SCENARIO")} title={tx("Así cambiaría tu plan", "How your plan would change")} caption={tx("Comparado con tu plan actual.", "Compared with your current plan.")}/><Card title={tx("Plan actual", "Current plan")}><DataRow label={tx("Margen mensual", "Monthly margin")} value={money(result.current?.strategic_margin)}/></Card><Card title={tx("Escenario VIP", "VIP scenario")} tone="violet"><DataRow label={tx("Margen mensual", "Monthly margin")} value={money(result.scenario?.strategic_margin)} tone="mint"/><DataRow label={tx("Cambio", "Change")} value={money(result.delta?.strategic_margin)} tone={Number(result.delta?.strategic_margin) >= 0 ? "mint" : "coral"}/></Card><PrimaryButton onClick={() => setMode("builder")}>{tx("Ajustar escenario", "Adjust scenario")}</PrimaryButton></section>;
  return <section className="vip-screen"><VipHeader title={tx("Escenarios", "Scenarios")} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("PROBÁ SIN CAMBIAR TUS DATOS", "TRY WITHOUT CHANGING YOUR DATA")} title={tx("¿Qué pasaría si...?", "What if…?")} caption={tx("Simulaciones separadas de tu plan real.", "Simulations separate from your real plan.")}/>{examples.map(([title, caption, tone]) => <button className={`vip-link-card vip-link-card--${tone}`} type="button" key={title} onClick={() => setMode("builder")}><span><strong>{title}</strong><small>{caption}</small></span><ChevronRight size={17}/></button>)}<PrimaryButton onClick={() => setMode("builder")}>{tx("＋ Nuevo escenario", "＋ New scenario")}</PrimaryButton></section>;
}

function VipSmartGoal({ data, user, onNavigate }) {
  const goal = data.goals?.[0];
  if (!goal) return <section className="vip-screen"><VipHeader title={tx("Meta inteligente", "Smart goal")} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("META INTELIGENTE", "SMART GOAL")} title={tx("Creá tu primera meta", "Create your first goal")} caption={tx("Cuando agregués una meta, DINCR calculará un ritmo compatible con tu estrategia.", "When you add a goal, DINCR will calculate a pace compatible with your strategy.")}/><button className="vip-link-card" type="button" onClick={() => onNavigate?.("more")}><span><strong>{tx("Planificación", "Planning")}</strong><small>{tx("Administrá metas desde las herramientas de planificación.", "Manage goals from the planning tools.")}</small></span><ChevronRight size={17}/></button></section>;
  const target = Number(goal.target_amount) || 0, current = Number(goal.current_amount) || 0;
  const completion = target ? Math.min(current / target * 100, 100) : 0;
  return <section className="vip-screen"><VipHeader title={goal.name} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("META INTELIGENTE", "SMART GOAL")} title={`${percent(completion)} ${tx("completada", "complete")}`} caption={`${money(current)} ${tx("de", "of")} ${money(target)}`}/><Card title={tx("Plan recomendado", "Recommended plan")} tone="gold"><DataRow label={tx("Aporte mensual", "Monthly contribution")} value={goal.monthly_required == null ? "—" : money(goal.monthly_required)} tone="violet"/><DataRow label={tx("Meses restantes", "Months remaining")} value={goal.months_left == null ? "—" : String(goal.months_left)} tone="mint"/><DataRow label={tx("Falta", "Remaining")} value={money(goal.remaining)}/></Card><Card title={tx("Protección estratégica", "Strategic protection")}><p className={goal.viable ? "vip-text-mint" : "vip-text-gold"}>{goal.viable ? tx("Este aporte respeta tu fondo de emergencia y tu mínimo personal.", "This contribution respects your emergency fund and personal minimum.") : tx("Esta meta requiere ajustar el plan actual.", "This goal requires adjusting the current plan.")}</p></Card><PrimaryButton onClick={() => onNavigate?.("vip-scenarios")}>{tx("Simular un cambio", "Simulate a change")}</PrimaryButton></section>;
}

function VipEmergency({ profile, data, user, onNavigate }) {
  const saved = Number(profile.liquid_savings) || 0, target = Number(profile.emergency_fund_target) || 0;
  const progress = target ? Math.min(saved / target * 100, 100) : 0;
  const essentials = Number(profile.essential_monthly_expenses) || 0;
  const contribution = Math.max(0, Math.min(Number(data.safe_to_spend?.monthly_margin) || 0, target - saved));
  return <section className="vip-screen"><VipHeader title={tx("Fondo de emergencia", "Emergency fund")} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("OBJETIVO VIP", "VIP TARGET")} title={`${money(saved)} / ${money(target)}`} caption={`${percent(progress)} ${tx("protegido", "protected")}`} tone="gold"><progress max="100" value={progress}/></Focus><Card title={tx("Ritmo recomendado", "Recommended pace")} tone="violet"><DataRow label={tx("Aporte mensual", "Monthly contribution")} value={money(contribution)} tone="violet"/><DataRow label={tx("Falta para el objetivo", "Remaining to target")} value={money(Math.max(target - saved, 0))} tone="mint"/><DataRow label={tx("Cobertura actual", "Current coverage")} value={`${essentials ? (saved / essentials).toFixed(1) : "0.0"} ${tx("meses", "months")}`} tone="gold"/></Card><Card title={tx("Por qué importa", "Why it matters")} tone="gold"><p>{tx("DINCR protege este fondo antes de aumentar aportes opcionales a metas.", "DINCR protects this fund before increasing optional goal contributions.")}</p></Card><PrimaryButton onClick={() => onNavigate?.("vip-preferences")}>{tx("Ajustar objetivo", "Adjust target")}</PrimaryButton></section>;
}

function VipReality({ data, budget, user, onNavigate }) {
  const items = budget?.items || [];
  const planned = items.reduce((sum, item) => sum + Number(item.monthly_limit || 0), 0);
  const spent = items.reduce((sum, item) => sum + Number(item.spent || 0), 0);
  const delta = planned - spent;
  const groups = [
    [tx("Gastos esenciales", "Essential expenses"), planned, spent],
    [tx("Deudas", "Debts"), Number(data.debt_planner?.recommended?.monthly_to_target) || 0, Number(data.reports?.current?.debt_paid) || 0],
    [tx("Ahorro", "Savings"), Number(data.safe_to_spend?.monthly_margin) || 0, Math.max(Number(data.reports?.current?.balance) || 0, 0)],
  ];
  return <section className="vip-screen"><VipHeader title={tx("Plan vs realidad", "Plan vs reality")} user={user} onNavigate={onNavigate}/><Focus eyebrow={new Intl.DateTimeFormat(localeTag(language), {month:"long"}).format(new Date()).toUpperCase()} title={delta >= 0 ? tx(`${money(delta)} mejor que el plan`, `${money(delta)} better than plan`) : tx(`${money(Math.abs(delta))} sobre el plan`, `${money(Math.abs(delta))} over plan`)} caption={tx("DINCR puede reajustar el próximo mes con este resultado.", "DINCR can readjust next month using this result.")} tone={delta >= 0 ? "mint" : "coral"}/>{groups.map(([name, plan, actual]) => <Card key={name} title={name}><DataRow label={`${tx("Plan", "Plan")} ${money(plan)}`} value={`${tx("Real", "Actual")} ${money(actual)}`} tone={actual <= plan ? "mint" : "coral"}/></Card>)}<Card title={tx("Ajuste sugerido", "Suggested adjustment")} tone="gold"><p>{delta >= 0 ? tx("Protegé el excedente dentro de tu prioridad estratégica.", "Protect the surplus within your strategic priority.") : tx("Revisá las categorías sobre el plan antes del próximo mes.", "Review categories over plan before next month.")}</p></Card></section>;
}

function VipMonthlyReview({ user, onNavigate }) {
  const now = new Date();
  const currentPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const [period, setPeriod] = useState(currentPeriod);
  const [review, setReview] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setReview(null); setError("");
    getVipMonthlyReview(period).then(setReview).catch(() => setError(tx("No pudimos generar la revisión mensual.", "We couldn't generate the monthly review.")));
  }, [period]);
  if (error) return <section className="vip-screen"><VipHeader title={tx("Revisión mensual", "Monthly review")} user={user} onNavigate={onNavigate}/><Card tone="danger"><p>{error}</p></Card></section>;
  if (!review) return <LoadingScreen/>;
  const baseline = review.status === "BASELINE";
  return <section className="vip-screen">
    <VipHeader title={tx("Revisión mensual", "Monthly review")} user={user} onNavigate={onNavigate}/>
    <label className="vip-field"><span>{tx("Período", "Period")}</span><input type="month" max={currentPeriod} value={period} onChange={(event) => setPeriod(event.target.value || currentPeriod)}/></label>
    <Focus eyebrow={review.period} title={review.headline} caption={review.summary} tone={baseline ? "gold" : review.deviations?.length ? "coral" : "mint"}/>
    <Card title={tx("Lo que DINCR observó", "What DINCR observed")}>
      <DataRow label={tx("Observaciones del período", "Period observations")} value={review.coverage?.observations || 0}/>
      <DataRow label={tx("Cambios relevantes", "Relevant changes")} value={review.finva_value?.changes_detected || 0} tone="violet"/>
      <DataRow label={tx("Estrategia reajustada", "Strategy adjusted")} value={review.finva_value?.priority_updated ? tx("Sí", "Yes") : tx("No", "No")} tone={review.finva_value?.priority_updated ? "gold" : "mint"}/>
      <p>{review.finva_value?.explanation}</p>
    </Card>
    {!baseline && review.wins?.length > 0 && <Card title={tx("Progreso del mes", "Progress this month")} tone="mint">{review.wins.map((item) => <DataRow key={item.key} label={item.label} value={`${item.delta >= 0 ? "+" : ""}${item.unit === "CRC" ? money(item.delta) : item.delta}`} tone="mint"/>)}</Card>}
    {!baseline && review.deviations?.length > 0 && <Card title={tx("Desviaciones a corregir", "Deviations to correct")} tone="gold">{review.deviations.map((item) => <DataRow key={item.key} label={item.label} value={`${item.delta >= 0 ? "+" : ""}${item.unit === "CRC" ? money(item.delta) : item.delta}`} tone="coral"/>)}</Card>}
    {review.plan_vs_reality && <Card title={tx("Plan vs realidad", "Plan vs reality")}><DataRow label={tx("Planeado", "Planned")} value={money(review.plan_vs_reality.planned_amount)}/><DataRow label={tx("Real", "Actual")} value={review.plan_vs_reality.actual_amount == null ? "—" : money(review.plan_vs_reality.actual_amount)} tone={review.plan_vs_reality.status === "met" ? "mint" : "coral"}/></Card>}
    <Card title={tx("Prioridad del próximo mes", "Next month's priority")} tone="violet"><DataRow label={review.next_month?.title || "—"} value={review.next_month?.amount ? money(review.next_month.amount) : "—"} tone="violet"/><p>{review.next_month?.rationale}</p></Card>
  </section>;
}

function VipToday({ user, onNavigate }) {
  const [advisor, setAdvisor] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getVipProactiveAdvisor().then(setAdvisor).catch(() => setError(tx("No pudimos revisar cambios recientes.", "We couldn't review recent changes.")));
  }, []);
  if (error) return <section className="vip-screen"><VipHeader title="DINCR Today" user={user} onNavigate={onNavigate}/><Card tone="danger"><p>{error}</p></Card></section>;
  if (!advisor) return <LoadingScreen/>;
  const tone = advisor.summary?.urgent ? "coral" : advisor.summary?.positive ? "mint" : "violet";
  return <section className="vip-screen">
    <VipHeader title="DINCR Today" user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={advisor.as_of} title={advisor.status === "BASELINE" ? tx("DINCR empezó a observar", "DINCR started observing") : advisor.status === "STABLE" ? tx("Sin cambios importantes", "No meaningful changes") : tx("Hay cambios que merecen atención", "There are changes worth your attention")} caption={advisor.message} tone={tone}/>
    {advisor.alerts?.map((alert) => <Card key={alert.id} title={alert.title} tone={alert.severity === "success" ? "mint" : alert.severity === "critical" || alert.severity === "high" ? "danger" : "gold"}><p>{alert.explanation}</p><PrimaryButton onClick={() => onNavigate?.(alert.action?.route)}>{alert.action?.label || tx("Revisar", "Review")}</PrimaryButton></Card>)}
    {!advisor.alerts?.length && <Card title={tx("Qué está observando DINCR", "What DINCR is watching")}><DataRow label={tx("Cambios urgentes", "Urgent changes")} value={advisor.summary?.urgent || 0} tone="mint"/><DataRow label={tx("Cambios a revisar", "Changes to review")} value={advisor.summary?.attention || 0} tone="mint"/><DataRow label={tx("Avances detectados", "Progress detected")} value={advisor.summary?.positive || 0} tone="mint"/></Card>}
  </section>;
}

function VipMore({ user, onNavigate, onLogout }) {
  const items = [
    ["vip-today", tx("DINCR Today", "DINCR Today"), tx("Alertas útiles y acciones basadas en cambios reales.", "Useful alerts and actions based on real changes.")],
    ["strategy", tx("Estrategia dinámica", "Dynamic strategy"), tx("Prioridades y acciones del mes.", "Priorities and actions for the month.")],
    ["vip-projections", tx("Proyecciones", "Projections"), tx("Mirá hacia dónde van tus números.", "See where your numbers are going.")],
    ["vip-scenarios", tx("Escenarios", "Scenarios"), tx("Probá decisiones sin cambiar datos.", "Try decisions without changing data.")],
    ["vip-reality", tx("Plan vs realidad", "Plan vs reality"), tx("Compará lo planeado con lo ocurrido.", "Compare what was planned with what happened.")],
    ["vip-monthly-review", tx("Revisión mensual DINCR", "DINCR monthly review"), tx("Entendé qué cambió y cómo se reajusta tu estrategia.", "Understand what changed and how your strategy adapts.")],
    ["vip-emergency", tx("Fondo de emergencia", "Emergency fund"), tx("Protegé tu colchón financiero.", "Protect your financial cushion.")],
    ["vip-aguinaldo", tx("Aguinaldo", "Annual bonus"), tx("Calculalo con tus órdenes patronales de la CCSS.", "Calculate it from your CCSS payroll orders.")],
  ];
  return <section className="vip-screen"><VipHeader title={tx("Más", "More")} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("INTELIGENCIA VIP", "VIP INTELLIGENCE")}/>{items.map(([key, title, caption]) => <button className="vip-link-card" type="button" key={key} onClick={() => onNavigate?.(key)}><span><strong>{title}</strong><small>{caption}</small></span><ChevronRight size={17}/></button>)}<button className="vip-link-card vip-link-card--blue" type="button" onClick={() => onNavigate?.("budget")}><span><strong>{tx("Planificación Basic", "Basic planning")}</strong><small>{tx("Presupuesto · Calendario · Recurrentes · Reportes", "Budget · Calendar · Recurring · Reports")}</small></span><ChevronRight size={17}/></button><button className="vip-link-card" type="button" onClick={() => onNavigate?.("gmail")}><span><strong>{tx("Movimientos desde Gmail", "Transactions from Gmail")}</strong><small>{tx("Automatización bancaria de solo lectura.", "Read-only banking automation.")}</small></span><ChevronRight size={17}/></button><button className="vip-link-card" type="button" onClick={() => onNavigate?.("settings")}><span><strong>{tx("Ajustes de cuenta y plan", "Account and plan settings")}</strong><small>{tx("Perfil, apariencia, seguridad y cambio de plan.", "Profile, appearance, security, and plan changes.")}</small></span><ChevronRight size={17}/></button><button className="vip-link-card" type="button" onClick={() => onNavigate?.("feedback")}><span><strong>{tx("Ayuda y soporte", "Help & support")}</strong><small>{tx("Reportá un problema o compartí una sugerencia.", "Report a problem or share feedback.")}</small></span><ChevronRight size={17}/></button><AccountActions onLogout={onLogout} variant="vip"/></section>;
}

function VipAguinaldo({ user, onNavigate }) {
  const [gmail, setGmail] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try {
      const status = await getVipGmailStatus();
      setGmail(status);
      if (status?.connected) setReport(await getVipAguinaldo());
      else setReport(null);
    } catch (reason) {
      setError(reason?.message || tx("No pudimos calcular tu aguinaldo.", "We couldn't calculate your annual bonus."));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const synchronize = async () => {
    setSyncing(true); setError("");
    try {
      await syncVipGmail();
      setReport(await getVipAguinaldo());
    } catch (reason) {
      setError(reason?.message || tx("No pudimos sincronizar tus órdenes patronales.", "We couldn't sync your payroll orders."));
    } finally { setSyncing(false); }
  };

  if (loading) return <LoadingScreen/>;
  if (!gmail?.connected) return <section className="vip-screen">
    <VipHeader title={tx("Aguinaldo", "Annual bonus")} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={tx("DATOS OFICIALES CCSS", "OFFICIAL CCSS DATA")} title={tx("Debes sincronizar tu email", "You must sync your email")} caption={tx("DINCR necesita leer tus órdenes patronales de la CCSS para calcular el aguinaldo con salarios oficiales.", "DINCR needs to read your CCSS payroll orders to calculate your annual bonus from official salaries.")} tone="gold"/>
    <Card title={tx("Permiso de solo lectura", "Read-only access")}><p><ShieldCheck size={16}/>{tx("DINCR no puede enviar, modificar ni borrar tus correos.", "DINCR cannot send, modify, or delete your emails.")}</p></Card>
    {error && <Card tone="danger"><p>{error}</p></Card>}
    <PrimaryButton onClick={() => onNavigate?.("gmail")}><Mail size={18}/>{tx("Sincronizar email", "Sync email")}</PrimaryButton>
  </section>;

  const months = report?.months || [];
  return <section className="vip-screen">
    <VipHeader title={tx("Aguinaldo", "Annual bonus")} user={user} onNavigate={onNavigate}/>
    <Focus eyebrow={tx("ACUMULADO ESTIMADO", "ESTIMATED ACCRUED")} title={money(report?.accrued_aguinaldo)} caption={tx("Salarios oficiales del período ÷ 12", "Official salaries in the period ÷ 12")} tone="mint"/>
    <Card title={tx("Datos utilizados", "Data used")}>
      <DataRow label={tx("Salario computable", "Eligible salary")} value={money(report?.earned_salary_total)}/>
      <DataRow label={tx("Última orden disponible", "Latest available order")} value={report?.period?.official_through || "—"}/>
      <DataRow label={tx("Meses pendientes", "Missing months")} value={report?.missing_months?.length || 0} tone="gold"/>
    </Card>
    <Card title={tx("Desglose mensual", "Monthly breakdown")}>{months.map((item) => <DataRow key={item.month} label={item.month} value={item.entries ? money(item.total_earned) : tx("Pendiente", "Pending")} tone={item.entries ? "mint" : "gold"}/>)}</Card>
    <Card tone="gold"><p>{tx("DINCR usa únicamente el salario oficial de cada Orden Patronal de la CCSS. No estima meses faltantes con movimientos bancarios.", "DINCR only uses the official salary from each CCSS payroll order. It does not estimate missing months from bank transactions.")}</p></Card>
    {error && <Card tone="danger"><p>{error}</p></Card>}
    <PrimaryButton disabled={syncing} onClick={synchronize}><RefreshCw size={18}/>{syncing ? tx("Sincronizando…", "Syncing…") : tx("Sincronizar email y recalcular", "Sync email and recalculate")}</PrimaryButton>
  </section>;
}

function VipPreferences({ profile, user, onNavigate, reload }) {
  const [form, setForm] = useState({...profile});
  const [saving, setSaving] = useState(false), [message, setMessage] = useState("");
  const save = async (event) => {
    event.preventDefault(); setSaving(true); setMessage("");
    try {
      await updateFinancialSituation({...form, emergency_fund_target:Number(form.emergency_fund_target) || 0, discretionary_monthly_minimum:Number(form.discretionary_monthly_minimum) || 0});
      setMessage(tx("Preferencias guardadas.", "Preferences saved.")); await reload();
    } catch { setMessage(tx("No pudimos guardar los cambios.", "We couldn't save your changes.")); }
    finally { setSaving(false); }
  };
  return <section className="vip-screen"><VipHeader title={tx("Preferencias VIP", "VIP preferences")} user={user} onNavigate={onNavigate}/><Focus eyebrow={tx("ESTRATEGIA PERSONAL", "PERSONAL STRATEGY")} caption={tx("DINCR adapta sus recomendaciones a estas reglas.", "DINCR adapts its recommendations to these rules.")}/><form className="vip-form" onSubmit={save}><label className="vip-field"><span>{tx("Prioridad", "Priority")}</span><select value={form.strategy_preference || "balanced"} onChange={(e) => setForm({...form, strategy_preference:e.target.value})}><option value="balanced">{tx("Equilibrado", "Balanced")}</option><option value="debt">{tx("Deuda", "Debt")}</option><option value="emergency">{tx("Emergencia", "Emergency")}</option><option value="goals">{tx("Metas", "Goals")}</option></select></label><label className="vip-field"><span>{tx("Fondo de emergencia", "Emergency fund")}</span><input type="number" min="0" value={form.emergency_fund_target ?? 0} onChange={(e) => setForm({...form, emergency_fund_target:e.target.value})}/></label><label className="vip-field"><span>{tx("Mínimo para gustos", "Personal minimum")}</span><input type="number" min="0" value={form.discretionary_monthly_minimum ?? 0} onChange={(e) => setForm({...form, discretionary_monthly_minimum:e.target.value})}/></label><Card title={tx("Cómo usa DINCR estos datos", "How DINCR uses this data")} tone="gold"><p><ShieldCheck size={16}/>{tx("Protege tus límites antes de sugerir pagos, ahorro o aportes a metas.", "It protects your limits before suggesting payments, savings, or goal contributions.")}</p></Card>{message && <p className="vip-form-message"><Sparkles size={15}/>{message}</p>}<button className="vip-primary" disabled={saving}>{saving ? tx("Guardando…", "Saving…") : tx("Guardar preferencias", "Save preferences")}</button></form></section>;
}
