import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldAlert, TrendingDown, WalletCards } from "lucide-react";
import { getFinancialDeterioration } from "../services/jarvisApi";

const crc = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;
const labels = { liquidity: "Liquidez", debt_payments: "Deuda", expenses: "Gastos", salvavidas: "Salvavidas", available_cash: "Efectivo" };

export default function FinancialDeterioration() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  const load = async () => { setState((s) => ({ ...s, loading: true, error: "" })); try { setState({ loading: false, data: await getFinancialDeterioration(), error: "" }); } catch (e) { setState({ loading: false, data: null, error: e.message || "No pude analizar el deterioro financiero." }); } };
  useEffect(() => { load(); }, []);
  if (state.loading) return <section className="hud-panel">Analizando tendencia financiera...</section>;
  if (state.error) return <section className="hud-panel strategy-warning">{state.error}</section>;
  const data = state.data || {}; const ctx = data.context || {}; const primary = data.primary_cause;
  return <section className="deterioration-page"><div className="hud-panel deterioration-hero"><div><span className="strategy-eyebrow">JARVIS 11 · EARLY WARNING</span><h2>Deterioro financiero</h2><p>Comparación de periodos para detectar señales negativas antes de que se conviertan en una crisis.</p></div><button className="strategy-refresh-btn" onClick={load}><RefreshCw size={17}/> Actualizar</button><div className={`deterioration-status ${data.health}`}><span>{data.health === "stable" ? <CheckCircle2/> : <ShieldAlert/>} Estado general</span><strong>{data.health === "deteriorating" ? "En deterioro" : data.health === "watch" ? "Para vigilar" : "Estable"}</strong><small>Periodo: {data.period?.current || "actual"}</small></div></div>
    <div className="deterioration-kpis"><article className="hud-card"><WalletCards/><span>Liquidez disponible</span><strong>{crc(ctx.liquidity_available)}</strong></article><article className="hud-card"><ShieldAlert/><span>Cobertura Salvavidas</span><strong>{Number(ctx.salvavidas_coverage_months || 0).toFixed(2)} meses</strong></article><article className="hud-card"><TrendingDown/><span>Deuda pendiente</span><strong>{crc(ctx.debt_balance)}</strong></article><article className="hud-card"><AlertTriangle/><span>Recurrentes esperados</span><strong>{crc(ctx.recurring_expected)}</strong></article></div>
    <div className="hud-panel deterioration-primary"><span className="strategy-eyebrow">CAUSA PRINCIPAL</span>{primary ? <><h3>{primary.title}</h3><p>{primary.context}</p><div><strong>{labels[primary.code] || primary.code}</strong><span>Actual: {primary.metric.toLocaleString("es-CR")} · Comparación: {primary.comparison.toLocaleString("es-CR")} {primary.unit}</span></div></> : <><h3>No se detecta deterioro relevante</h3><p>JARVIS no encontró cambios negativos que superen los umbrales definidos con los datos disponibles.</p></>}</div>
    <div className="hud-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">SEÑALES DETECTADAS</span><h3>Qué está cambiando</h3></div><small>Sin acciones automáticas</small></div>{data.signals?.length ? <div className="deterioration-signals">{data.signals.map((item) => <article className={`deterioration-signal ${item.severity}`} key={item.code}><span>{labels[item.code] || item.code}</span><strong>{item.title}</strong><p>{item.context}</p></article>)}</div> : <p className="muted-text">Todavía no hay señales suficientes para comparar.</p>}</div>
    <div className="hud-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">HISTORIAL COMPARABLE</span><h3>Flujo por periodo</h3></div></div><div className="deterioration-months">{(data.monthly || []).map((item) => <div key={item.month}><strong>{item.month}</strong><span>Ingresos {crc(item.income)}</span><span>Gastos {crc(item.expenses)}</span><b className={item.net < 0 ? "negative" : "positive"}>{item.net >= 0 ? "+" : "−"}{crc(Math.abs(item.net))}</b></div>)}</div></div>
    <div className="hud-panel timeline-assumptions"><span className="strategy-eyebrow">REGLA DE SEGURIDAD</span><p>{data.note}</p></div>
  </section>;
}
