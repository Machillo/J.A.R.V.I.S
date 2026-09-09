import { Crown, ChevronRight, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { getBasicDashboard, getFinanceSummary } from "../services/jarvisApi";

const money = (value) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);
const trend = (value) => `${Number(value) >= 0 ? "+" : ""}${money(value)}`;

export default function Dashboard({ user, plan = "free", onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const advanced = plan === "basic" || plan === "vip";
  useEffect(() => { (advanced ? getBasicDashboard() : getFinanceSummary()).then(setData).catch((e) => setError(e.message)); }, [advanced]);
  if (error) return <div className="panel error">{error}</div>;
  if (!data) return <div className="panel">Cargando resumen...</div>;
  const balance = data.balance ?? data.available_after_commitments;
  const maxCategory = Math.max(...(data.categories || []).map((x) => Number(x.amount)), 1);
  return <section className={`dashboard-plan dashboard-${plan}`}>
    <div className="hero"><span>Hola {user?.display_name || ""}</span><h1>Tu panorama financiero</h1><p>{data.month}</p></div>
    <div className="kpis">
      <div className="card"><small>Ingresos</small><strong>{money(data.income)}</strong>{advanced && <em>{trend(data.trends?.income)} vs anterior</em>}</div>
      <div className="card"><small>Gastos</small><strong>{money(data.expenses)}</strong>{advanced && <em>{trend(data.trends?.expenses)} vs anterior</em>}</div>
      <div className="card"><small>Balance del mes</small><strong className={Number(balance) < 0 ? "negative" : ""}>{money(balance)}</strong></div>
      <div className="card"><small>Deuda pendiente</small><strong>{money(data.debt?.remaining ?? data.debt_balance)}</strong>{advanced && <em>{data.debt?.progress || 0}% pagado</em>}</div>
      {advanced && <><div className="card"><small>Ahorro líquido</small><strong>{money(data.savings)}</strong></div><div className="card"><small>Metas</small><strong>{data.goals?.progress || 0}%</strong><em>{data.goals?.active || 0} activas</em></div></>}
    </div>
    {advanced && <>
      <div className="panel basic-chart"><h3>Ingresos vs gastos · 6 meses</h3>{(data.monthly_history || []).map((row) => { const max=Math.max(Number(row.income),Number(row.expenses),1); return <div className="history-row" key={row.month}><small>{row.month}</small><span><i style={{width:`${Number(row.income)/max*100}%`}}/><b>{money(row.income)}</b></span><span className="expense"><i style={{width:`${Number(row.expenses)/max*100}%`}}/><b>{money(row.expenses)}</b></span></div>; })}</div>
      <div className="panel basic-chart"><h3>Gastos por categoría</h3>{(data.categories || []).length ? data.categories.map((row)=><div className="category-bar" key={row.category}><span>{row.category}</span><i style={{width:`${Number(row.amount)/maxCategory*100}%`}}/><b>{money(row.amount)}</b></div>):<p>Sin gastos registrados este mes.</p>}</div>
    </>}
    {plan === "free" && <button className="dashboard-plan-action free" onClick={() => onNavigate?.("situation")}><span><strong>Completá tu base financiera</strong><small>Gratis organiza tus datos sin mostrar módulos Basic.</small></span><ChevronRight size={20}/></button>}
    {plan === "basic" && <button className="dashboard-plan-action basic" onClick={() => onNavigate?.("budget")}><Sparkles size={21}/><span><strong>Abrir presupuesto guiado</strong><small>Distribuí el ingreso disponible por categorías.</small></span><ChevronRight size={20}/></button>}
    {plan === "vip" && <button className="dashboard-plan-action vip" onClick={() => onNavigate?.("strategy")}><Crown size={21}/><span><strong>Abrir Dirección VIP</strong><small>Tu experiencia VIP incluye toda la base Basic.</small></span><ChevronRight size={20}/></button>}
  </section>;
}
