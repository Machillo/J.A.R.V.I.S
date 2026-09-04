import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, CalendarDays, RefreshCw, Target, WalletCards } from "lucide-react";
import { getFinancialTimeline } from "../services/jarvisApi";

const crc = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;
const dateLabel = (value) => new Date(`${value}T12:00:00`).toLocaleDateString("es-CR", { day: "numeric", month: "short" });
const kinds = { income: "Ingreso", recurring_expense: "Recurrente", debt_payment: "Cuota", goal: "Meta" };

export default function FinancialTimeline() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  const load = async () => {
    setState((old) => ({ ...old, loading: true, error: "" }));
    try { setState({ loading: false, data: await getFinancialTimeline(), error: "" }); }
    catch (error) { setState({ loading: false, data: null, error: error.message || "No pude construir la línea de tiempo." }); }
  };
  useEffect(() => { load(); }, []);
  if (state.loading) return <section className="hud-panel">Calculando liquidez futura...</section>;
  if (state.error) return <section className="hud-panel strategy-warning">{state.error}</section>;
  const data = state.data || {};
  const events = data.events || [];
  return <section className="financial-timeline-page">
    <div className="hud-panel financial-timeline-hero">
      <div><span className="strategy-eyebrow">JARVIS 07 · LIQUIDITY MAP</span><h2>Timeline financiero</h2><p>Cómo cambia tu saldo disponible con los ingresos, obligaciones y compromisos conocidos.</p></div>
      <button className="strategy-refresh-btn" onClick={load}><RefreshCw size={17}/> Actualizar</button>
      <div className="timeline-kpis"><div><WalletCards size={18}/><span>Disponible hoy</span><strong>{crc(data.opening_available)}</strong></div><div><CalendarDays size={18}/><span>Al cierre proyectado</span><strong className={Number(data.ending_available) < 0 ? "negative" : "positive"}>{crc(data.ending_available)}</strong></div><div><Target size={18}/><span>Eventos</span><strong>{data.event_count || 0}</strong></div></div>
    </div>
    <div className="hud-panel timeline-list-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">PRÓXIMOS 45 DÍAS</span><h3>Saldo después de cada evento</h3></div><small>{data.start_date} → {data.end_date}</small></div>
      {events.length ? <div className="financial-timeline-list">{events.map((event, index) => { const incoming = Number(event.impact) >= 0; return <article className={`financial-timeline-item ${incoming ? "timeline-in" : "timeline-out"}`} key={`${event.date}-${event.name}-${index}`}><div className="timeline-marker">{incoming ? <ArrowUpRight size={17}/> : event.kind === "goal" ? <Target size={17}/> : <ArrowDownRight size={17}/>}</div><div className="timeline-event-copy"><div><strong>{event.name}</strong><span>{dateLabel(event.date)} · {kinds[event.kind] || "Compromiso"}</span></div>{event.note && <small>{event.note}</small>}</div><div className="timeline-event-values"><strong>{event.kind === "goal" ? crc(event.amount) : `${incoming ? "+" : "−"}${crc(event.amount)}`}</strong><small>Saldo {crc(event.projected_balance)}</small></div></article>; })}</div> : <div className="timeline-empty"><CalendarDays size={30}/><p>No hay eventos fechados para proyectar todavía.</p><small>Configurá calendario de pago y obligaciones activas para que JARVIS los incorpore.</small></div>}
    </div>
    <div className="hud-panel timeline-assumptions"><span className="strategy-eyebrow">CRITERIO DE CÁLCULO</span>{(data.assumptions || []).map((item) => <p key={item}>· {item}</p>)}</div>
  </section>;
}
