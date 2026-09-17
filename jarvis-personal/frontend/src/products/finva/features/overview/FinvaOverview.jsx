import { ChevronRight, Crown, PiggyBank, Sparkles, TrendingDown, TrendingUp, WalletCards } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getBasicDashboard, getFreeDashboard } from "../../../../users/services/jarvisApi";
import "./overview.css";

const money = (value) => new Intl.NumberFormat("es-CR", {
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
  if (!data) return <div className="mobile-panel finva-overview-state">Preparando tu resumen...</div>;

  return (
    <section className={`finva-overview dashboard-${plan}`}>
      <header className="finva-overview-hero">
        <span>{advanced ? "TU PANORAMA" : "TU PUNTO DE PARTIDA"}</span>
        <h1>Hola, {user?.display_name || "bienvenido"}</h1>
        <p>Estos son tus números de {data.month}. Empezá por entenderlos; después decidimos el siguiente paso.</p>
      </header>

      <div className="finva-overview-metrics">
        <MetricCard label="Ingresos" value={money(data.income)} detail={advanced ? `${change(data.trends?.income)} vs. mes anterior` : "Este mes"} tone="positive" icon={TrendingUp} />
        <MetricCard label="Gastos" value={money(data.expenses)} detail={advanced ? `${change(data.trends?.expenses)} vs. mes anterior` : "Este mes"} tone="negative" icon={TrendingDown} />
        <MetricCard label="Disponible" value={money(computed.balance)} tone={Number(computed.balance) < 0 ? "negative" : "accent"} icon={WalletCards} />
        <MetricCard label="Deuda pendiente" value={money(data.debt?.remaining ?? data.debt_balance)} detail={advanced ? `${data.debt?.progress || 0}% pagado` : "Total registrado"} icon={WalletCards} />
        {advanced ? <MetricCard label="Ahorro disponible" value={money(data.savings)} icon={PiggyBank} tone="positive" /> : null}
        {advanced ? <MetricCard label="Metas" value={`${data.goals?.progress || 0}%`} detail={`${data.goals?.active || 0} activas`} icon={Sparkles} tone="accent" /> : null}
      </div>

      <article className="mobile-panel finva-overview-chart">
        <header><div><small>ÚLTIMOS 6 MESES</small><h2>Ingresos y gastos</h2></div></header>
        {computed.history.length ? computed.history.map((row) => (
          <div className="finva-overview-chart-row" key={row.month}>
            <small>{row.month.slice(5)}</small>
            <div><span className="income" style={{ width: `${Number(row.income) / computed.maxMonth * 100}%` }} /></div>
            <div><span className="expense" style={{ width: `${Number(row.expenses) / computed.maxMonth * 100}%` }} /></div>
          </div>
        )) : <p className="finva-overview-empty">Agregá tus primeros movimientos para ver la comparación mensual.</p>}
        <footer><span><i className="income" /> Ingresos</span><span><i className="expense" /> Gastos</span></footer>
      </article>

      <article className="mobile-panel finva-overview-categories">
        <header><div><small>EN QUÉ SE VA</small><h2>Gastos por categoría</h2></div></header>
        {computed.categories.length ? computed.categories.map((item) => (
          <div key={item.category}>
            <span>{item.category}</span><strong>{money(item.amount)}</strong>
            <i><b style={{ width: `${Number(item.amount) / computed.maxCategory * 100}%` }} /></i>
          </div>
        )) : <p className="finva-overview-empty">Cuando registrés gastos, los agruparemos acá automáticamente.</p>}
      </article>

      {plan === "free" && <button className="finva-overview-action" onClick={() => onNavigate?.("monthly")}><span><strong>Ver resumen mensual</strong><small>Revisá tus números con más detalle.</small></span><ChevronRight /></button>}
      {plan === "basic" && <button className="finva-overview-action" onClick={() => onNavigate?.("budget")}><Sparkles /><span><strong>Abrir presupuesto guiado</strong><small>Asigná tu ingreso con intención.</small></span><ChevronRight /></button>}
      {plan === "vip" && <button className="finva-overview-action vip" onClick={() => onNavigate?.("strategy")}><Crown /><span><strong>Abrir Dirección VIP</strong><small>Tu estrategia financiera completa.</small></span><ChevronRight /></button>}
    </section>
  );
}
