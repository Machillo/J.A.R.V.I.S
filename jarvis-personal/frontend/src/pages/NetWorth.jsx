import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Landmark, RefreshCw, Scale, TrendingDown, TrendingUp, WalletCards } from "lucide-react";
import { getNetWorth } from "../services/jarvisApi";

const crc = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;
const compact = (value) => new Intl.NumberFormat("es-CR", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
const day = (value) => String(value || "").slice(5).replace("-", "/");

export default function NetWorth() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  const load = async () => {
    setState((old) => ({ ...old, loading: true, error: "" }));
    try { setState({ loading: false, data: await getNetWorth(), error: "" }); }
    catch (error) { setState({ loading: false, data: null, error: error.message || "No pude calcular el patrimonio." }); }
  };
  useEffect(() => { load(); }, []);

  if (state.loading) return <section className="hud-panel">Calculando patrimonio real...</section>;
  if (state.error) return <section className="hud-panel strategy-warning">{state.error}</section>;

  const data = state.data || {};
  const assets = data.assets || {};
  const liabilities = data.liabilities || {};
  const change = data.change || {};
  const positiveChange = Number(change.amount || 0) >= 0;
  const history = data.history || [];

  return <section className="net-worth-page">
    <div className="hud-panel net-worth-hero">
      <div><span className="strategy-eyebrow">JARVIS 06 · LIVE WEALTH</span><h2>Patrimonio neto</h2><p>Todo lo que tenés menos todo lo que debés, usando únicamente saldos reales.</p></div>
      <button className="strategy-refresh-btn" onClick={load}><RefreshCw size={17}/> Actualizar</button>
      <div className="net-worth-total"><span>Patrimonio actual</span><strong className={Number(data.net_worth) < 0 ? "negative" : "positive"}>{crc(data.net_worth)}</strong><small>{data.interpretation}</small></div>
    </div>

    <div className="net-worth-kpis">
      <article className="hud-card"><WalletCards/><span>Activos líquidos</span><strong>{crc(assets.savings_total)}</strong><small>MultiMoney, Salvavidas, efectivo y cuentas</small></article>
      <article className="hud-card"><TrendingUp/><span>Inversiones</span><strong>{crc(assets.investments_total)}</strong><small>IBKR y otras inversiones verificadas</small></article>
      <article className="hud-card"><TrendingDown/><span>Pasivos</span><strong className="negative">{crc(liabilities.debt_total)}</strong><small>Préstamos, deudas y cuentas negativas</small></article>
      <article className="hud-card"><Scale/><span>Cambio</span><strong className={positiveChange ? "positive" : "negative"}>{positiveChange ? "+" : ""}{crc(change.amount)}</strong><small>{change.compared_with ? `Desde ${change.compared_with}` : "Primer snapshot registrado"}</small></article>
    </div>

    <article className="hud-panel net-worth-chart-panel">
      <div className="panel-heading"><div><span className="strategy-eyebrow">EVOLUCIÓN REAL</span><h3>Historial del patrimonio</h3></div><small>Un cierre automático por día</small></div>
      {history.length > 1 ? <div className="net-worth-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={history}><defs><linearGradient id="wealthFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#72f2ae" stopOpacity={0.5}/><stop offset="95%" stopColor="#72f2ae" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="rgba(255,255,255,.07)" vertical={false}/><XAxis dataKey="snapshot_date" tickFormatter={day} stroke="#8da0a8"/><YAxis tickFormatter={compact} stroke="#8da0a8" width={58}/><Tooltip formatter={(value) => crc(value)} labelFormatter={(value) => `Fecha ${value}`}/><Area type="monotone" dataKey="net_worth" stroke="#72f2ae" fill="url(#wealthFill)" strokeWidth={3}/></AreaChart></ResponsiveContainer></div> : <div className="net-worth-empty-chart"><TrendingUp size={34}/><p>Hoy guardamos el primer punto. La gráfica crecerá automáticamente con cada día.</p></div>}
    </article>

    <div className="net-worth-columns">
      <article className="hud-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">ACTIVOS</span><h3>Dónde está tu patrimonio</h3></div><strong>{crc(assets.assets_total)}</strong></div><div className="net-worth-list">{[...(assets.savings || []), ...(assets.investments || [])].map((item, index) => <div key={`${item.name}-${index}`}><span><Landmark size={17}/>{item.name}</span><strong>{crc(item.amount)}</strong></div>)}</div></article>
      <article className="hud-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">PASIVOS</span><h3>Lo que debés</h3></div><strong className="negative">{crc(liabilities.debt_total)}</strong></div><div className="net-worth-list">{(liabilities.debts || []).map((item) => <div key={item.id}><span>{item.name}</span><strong>{crc(item.remaining_amount)}</strong></div>)}{!(liabilities.debts || []).length && <p className="muted-text">No hay deudas registradas.</p>}</div></article>
    </div>
  </section>;
}
