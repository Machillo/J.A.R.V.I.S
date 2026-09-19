import { ChevronRight, Crown, PiggyBank, Sparkles, TrendingDown, TrendingUp, WalletCards } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getBasicDashboard, getFreeDashboard } from "../../../../users/services/jarvisApi";
import "./overview.css";
import { deviceLanguage, localeTag } from "../../../../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => new Intl.NumberFormat(localeTag(language), {
  style: "currency",
  currency: "CRC",
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

const change = (value) => `${Number(value) >= 0 ? "+" : ""}${money(value)}`;

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

export default function FinvaOverview({ user, plan = "free", onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const advanced = plan === "basic" || plan === "vip";

  useEffect(() => {
    setError("");
    (advanced ? getBasicDashboard() : getFreeDashboard()).then(setData).catch((cause) => setError(cause.message));
  }, [advanced]);

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

  return (
    <section className={`finva-overview dashboard-${plan}`}>
      <header className="finva-overview-hero">
        <span>{advanced ? tx("TU PANORAMA", "YOUR OVERVIEW") : tx("TU PUNTO DE PARTIDA", "YOUR STARTING POINT")}</span>
        <h1>{tx("Hola", "Hello")}, {user?.display_name || tx("bienvenido", "welcome")}</h1>
        <p>{tx(`Estos son tus números de ${data.month}. Empezá por entenderlos; después decidimos el siguiente paso.`, `These are your numbers for ${data.month}. Understand them first; then we'll decide the next step.`)}</p>
      </header>

      <div className="finva-overview-metrics">
        <MetricCard label={tx("Ingresos", "Income")} value={money(data.income)} detail={advanced ? `${change(data.trends?.income)} ${tx("vs. mes anterior", "vs. previous month")}` : tx("Este mes", "This month")} tone="positive" icon={TrendingUp} />
        <MetricCard label={tx("Gastos", "Expenses")} value={money(data.expenses)} detail={advanced ? `${change(data.trends?.expenses)} ${tx("vs. mes anterior", "vs. previous month")}` : tx("Este mes", "This month")} tone="negative" icon={TrendingDown} />
        <MetricCard label={tx("Disponible", "Available")} value={money(computed.balance)} tone={Number(computed.balance) < 0 ? "negative" : "accent"} icon={WalletCards} />
        <MetricCard label={tx("Deuda pendiente", "Outstanding debt")} value={money(data.debt?.remaining ?? data.debt_balance)} detail={advanced ? `${data.debt?.progress || 0}% ${tx("pagado", "paid")}` : tx("Total registrado", "Recorded total")} icon={WalletCards} />
        {advanced ? <MetricCard label={tx("Ahorro disponible", "Available savings")} value={money(data.savings)} icon={PiggyBank} tone="positive" /> : null}
        {advanced ? <MetricCard label={tx("Metas", "Goals")} value={`${data.goals?.progress || 0}%`} detail={`${data.goals?.active || 0} ${tx("activas", "active")}`} icon={Sparkles} tone="accent" /> : null}
      </div>

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
            <span>{item.category}</span><strong>{money(item.amount)}</strong>
            <i><b style={{ width: `${Number(item.amount) / computed.maxCategory * 100}%` }} /></i>
          </div>
        )) : <p className="finva-overview-empty">{tx("Cuando registrés gastos, los agruparemos acá automáticamente.", "When you record expenses, we will group them here automatically.")}</p>}
      </article>

      {plan === "free" && <button className="finva-overview-action" onClick={() => onNavigate?.("monthly")}><span><strong>{tx("Ver resumen mensual", "View monthly summary")}</strong><small>{tx("Revisá tus números con más detalle.", "Review your numbers in more detail.")}</small></span><ChevronRight /></button>}
      {plan === "basic" && <button className="finva-overview-action" onClick={() => onNavigate?.("budget")}><Sparkles /><span><strong>{tx("Abrir presupuesto guiado", "Open guided budget")}</strong><small>{tx("Asigná tu ingreso con intención.", "Give every part of your income a purpose.")}</small></span><ChevronRight /></button>}
      {plan === "vip" && <button className="finva-overview-action vip" onClick={() => onNavigate?.("strategy")}><Crown /><span><strong>{tx("Abrir Dirección VIP", "Open VIP Direction")}</strong><small>{tx("Tu estrategia financiera completa.", "Your complete financial strategy.")}</small></span><ChevronRight /></button>}
    </section>
  );
}
