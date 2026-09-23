import { ChevronRight, Crown, PiggyBank, Sparkles, TrendingDown, TrendingUp, WalletCards } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getBasicDashboard, getBudget, getFinancialCalendar, getFreeDashboard } from "../../../../users/services/jarvisApi";
import "./overview.css";
import { deviceLanguage, localeTag } from "../../../../lib/locale";
import { categoryLabel } from "../../../../lib/categories";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => new Intl.NumberFormat(localeTag(language), {
  style: "currency",
  currency: "CRC",
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

const change = (value) => `${Number(value) >= 0 ? "+" : ""}${money(value)}`;
const currentPeriod = () => new Date().toISOString().slice(0, 7);

function MetricCard({ label, value, detail, tone = "neutral", icon: Icon }) {
  return (
    <article className={`finva-overview-metric tone-${tone}`}>
      <span className="finva-overview-metric-icon"><Icon size={19} /></span>
      <small>{label}</small>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </article>
  );
}

function BasicDashboard({ data, planning, onNavigate }) {
  const budget = planning?.budget;
  const calendar = planning?.calendar;
  const spent = (budget?.items || []).reduce((sum, item) => sum + Number(item.spent || 0), 0);
  const budgeted = Number(budget?.total_budgeted || 0);
  const used = budgeted > 0 ? Math.min(Math.round(spent / budgeted * 100), 100) : 0;
  const available = Math.max(Number(budget?.available_for_categories || 0) - spent, 0);
  const today = new Date();
  const limit = new Date(today);
  limit.setDate(limit.getDate() + 7);
  const upcoming = (calendar?.events || []).filter((item) => {
    const date = new Date(`${item.date}T12:00:00`);
    return date >= new Date(today.toDateString()) && date <= limit;
  }).slice(0, 2);

  return <section className="finva-basic-dashboard">
    <article className="finva-basic-hero-card">
      <small>{tx("DISPONIBLE PLANIFICADO", "PLANNED AVAILABLE")}</small>
      <strong>{money(budget ? available : data.balance)}</strong>
      <span>{budgeted ? tx(`Presupuesto usado ${used}%`, `Budget used ${used}%`) : tx("Configurá tu presupuesto para planificar el mes", "Set up your budget to plan the month")}</span>
    </article>

    <article className="finva-basic-quick-card">
      <button type="button" onClick={() => onNavigate?.("budget")}><span>{tx("Presupuesto mensual", "Monthly budget")}</span><b>{money(spent)} / {money(budgeted)}</b></button>
      <button type="button" onClick={() => onNavigate?.("calendar")}><span>{tx("Próximos compromisos", "Upcoming commitments")}</span><b>{money(calendar?.summary?.payments)}</b></button>
      <button type="button" onClick={() => onNavigate?.("goals")}><span>{tx("Ahorro del mes", "Savings this month")}</span><b className="positive">{money(data.savings)}</b></button>
    </article>

    <article className="finva-basic-upcoming">
      <header><strong>{tx("Próximos 7 días", "Next 7 days")}</strong><button type="button" onClick={() => onNavigate?.("calendar")}>{tx("Ver calendario", "View calendar")}</button></header>
      {upcoming.length ? upcoming.map((item) => <div key={`${item.date}-${item.name}`}>
        <span><b>{item.name}</b><small>{item.date.slice(8,10)} · {item.kind}</small></span>
        <strong>{item.amount ? money(item.amount) : "—"}</strong>
      </div>) : <p>{tx("No hay compromisos configurados para los próximos 7 días.", "No commitments are configured for the next 7 days.")}</p>}
    </article>

    <article className="finva-basic-plan-progress">
      <header><strong>{tx("Plan del mes", "Monthly plan")}</strong><b>{used}%</b></header>
      <progress max="100" value={used}/>
      <span>{used <= 100 ? tx("Vas dentro del presupuesto.", "You're within budget.") : tx("Revisá las categorías que superaron el plan.", "Review categories that exceeded the plan.")}</span>
    </article>
  </section>;
}

export default function FinvaOverview({ user, plan = "free", onNavigate }) {
  const [data, setData] = useState(null);
  const [planning, setPlanning] = useState(null);
  const [error, setError] = useState("");
  const advanced = plan === "basic" || plan === "vip";

  useEffect(() => {
    setError("");
    (advanced ? getBasicDashboard() : getFreeDashboard()).then(setData).catch((cause) => setError(cause.message));
  }, [advanced]);

  useEffect(() => {
    if (plan !== "basic") { setPlanning(null); return; }
    Promise.all([getBudget(), getFinancialCalendar(currentPeriod())])
      .then(([budget, calendar]) => setPlanning({ budget, calendar }))
      .catch(() => setPlanning({ budget: null, calendar: null }));
  }, [plan]);

  const computed = useMemo(() => {
    const categories = data?.categories || [];
    const history = data?.monthly_history || [];
    return {
      categories,
      history,
      balance: data?.balance ?? data?.available_after_commitments,
      maxCategory: Math.max(...categories.map((item) => Number(item.amount)), 1),
      maxMonth: Math.max(...history.flatMap((item) => [Number(item.income), Number(item.expenses)]), 1),
    };
  }, [data]);

  if (error) return <div className="mobile-panel finva-overview-state error">{error}</div>;
  if (!data) return <div className="mobile-panel finva-overview-state">{tx("Preparando tu resumen...", "Preparing your overview...")}</div>;

  if (plan === "basic") return <BasicDashboard data={data} planning={planning} onNavigate={onNavigate}/>;

  return (
    <section className={`finva-overview dashboard-${plan}`}>
      {advanced ? <>
        <header className="finva-overview-hero">
          <span>{tx("TU PANORAMA", "YOUR OVERVIEW")}</span>
          <h1>{tx("Hola", "Hello")}, {user?.display_name || tx("bienvenido", "welcome")}</h1>
          <p>{tx(`Estos son tus números de ${data.month}. Empezá por entenderlos; después decidimos el siguiente paso.`, `These are your numbers for ${data.month}. Understand them first; then we'll decide the next step.`)}</p>
        </header>
        <div className="finva-overview-metrics">
          <MetricCard label={tx("Ingresos", "Income")} value={money(data.income)} detail={`${change(data.trends?.income)} ${tx("vs. mes anterior", "vs. previous month")}`} tone="positive" icon={TrendingUp} />
          <MetricCard label={tx("Gastos", "Expenses")} value={money(data.expenses)} detail={`${change(data.trends?.expenses)} ${tx("vs. mes anterior", "vs. previous month")}`} tone="negative" icon={TrendingDown} />
          <MetricCard label={tx("Disponible", "Available")} value={money(computed.balance)} tone={Number(computed.balance) < 0 ? "negative" : "accent"} icon={WalletCards} />
          <MetricCard label={tx("Deuda pendiente", "Outstanding debt")} value={money(data.debt?.remaining ?? data.debt_balance)} detail={`${data.debt?.progress || 0}% ${tx("pagado", "paid")}`} icon={WalletCards} />
          <MetricCard label={tx("Ahorro disponible", "Available savings")} value={money(data.savings)} icon={PiggyBank} tone="positive" />
          <MetricCard label={tx("Metas", "Goals")} value={`${data.goals?.progress || 0}%`} detail={`${data.goals?.active || 0} ${tx("activas", "active")}`} icon={Sparkles} tone="accent" />
        </div>
      </> : <>
        <small className="finva-free-plan-label">{tx("Gratis", "Free")}</small>
        <article className="finva-free-available">
          <small>{tx("DISPONIBLE ESTE MES", "AVAILABLE THIS MONTH")}</small>
          <strong>{money(data.available_after_commitments ?? computed.balance)}</strong>
          <span>{tx("Ingresos", "Income")} {money(data.income)} · {tx("Gastos", "Expenses")} {money(data.expenses)}</span>
          <span>{tx("Deuda pagada", "Debt paid")} {money(data.debt_paid)}</span>
        </article>
        <article className="finva-free-kpis">
          <div><span>{tx("Ingresos", "Income")}</span><strong>{money(data.income)}</strong></div>
          <div><span>{tx("Gastos", "Expenses")}</span><strong>{money(data.expenses)}</strong></div>
          <div><span>{tx("Deuda pendiente", "Outstanding debt")}</span><strong>{money(data.debt_balance)}</strong></div>
        </article>
      </>}

      <article className="mobile-panel finva-overview-chart">
        <header><div><small>{tx("ÚLTIMOS 6 MESES", "LAST 6 MONTHS")}</small><h2>{tx("Ingresos y gastos", "Income and expenses")}</h2></div></header>
        {computed.history.length ? computed.history.map((row) => (
          <div className="finva-overview-chart-row" key={row.month}>
            <small>{row.month.slice(5)}</small>
            <div><span className="income" style={{ width: `${Number(row.income) / computed.maxMonth * 100}%` }} /></div>
            <div><span className="expense" style={{ width: `${Number(row.expenses) / computed.maxMonth * 100}%` }} /></div>
          </div>
        )) : <p className="finva-overview-empty">{tx("Agregá tus primeros movimientos para ver la comparación mensual.", "Add your first transactions to see the monthly comparison.")}</p>}
        <footer><span><i className="income" /> {tx("Ingresos", "Income")}</span><span><i className="expense" /> {tx("Gastos", "Expenses")}</span></footer>
      </article>

      <article className="mobile-panel finva-overview-categories">
        <header><div><small>{tx("EN QUÉ SE VA", "WHERE IT GOES")}</small><h2>{tx("Gastos por categoría", "Expenses by category")}</h2></div></header>
        {computed.categories.length ? computed.categories.map((item) => (
          <div key={item.category}>
            <span>{categoryLabel(item.category)}</span><strong>{money(item.amount)}</strong>
            <i><b style={{ width: `${Number(item.amount) / computed.maxCategory * 100}%` }} /></i>
          </div>
        )) : <p className="finva-overview-empty">{tx("Cuando registrés gastos, los agruparemos acá automáticamente.", "When you record expenses, we will group them here automatically.")}</p>}
      </article>

      {plan === "free" && <button className="finva-overview-action" onClick={() => onNavigate?.("monthly")}><span><strong>{tx("Ver resumen mensual", "View monthly summary")}</strong><small>{tx("Revisá tus números con más detalle.", "Review your numbers in more detail.")}</small></span><ChevronRight /></button>}
      {plan === "vip" && <button className="finva-overview-action vip" onClick={() => onNavigate?.("strategy")}><Crown /><span><strong>{tx("Abrir Dirección VIP", "Open VIP Direction")}</strong><small>{tx("Tu estrategia financiera completa.", "Your complete financial strategy.")}</small></span><ChevronRight /></button>}
    </section>
  );
}
