import { useEffect, useState } from "react";
import { ArrowDownToLine, Banknote, CircleDollarSign, RefreshCw, TrendingDown, TrendingUp, WalletCards } from "lucide-react";
import { getInvestmentCenter, getJarvisPremiumStrategyDashboard } from "../services/jarvisApi";

const crc = (v) => `₡${Math.round(Number(v || 0)).toLocaleString("es-CR")}`;
const usd = (v) => `$${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function Investments() {
  const [state, setState] = useState({ loading: true, center: null, strategy: null, error: "" });
  const load = async () => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const [center, strategy] = await Promise.all([getInvestmentCenter(), getJarvisPremiumStrategyDashboard()]);
      setState({ loading: false, center, strategy, error: "" });
    } catch (e) { setState((s) => ({ ...s, loading: false, error: e.message || "No pude cargar inversiones." })); }
  };
  useEffect(() => { load(); }, []);
  if (state.loading) return <section className="investments-page"><div className="hud-panel"><RefreshCw className="spin" /> Cargando inversiones...</div></section>;
  if (state.error) return <section className="investments-page"><div className="hud-panel strategy-warning">{state.error}</div></section>;

  const c = state.center || {}; const p = c.portfolio || {}; const s = state.strategy?.strategy || state.strategy || {};
  const positions = c.positions || [];
  const recommended = Number(s.investment_recommended || 0); const target = Number(s.investment_target || 5000);
  const net = Number(c.net_pnl || 0); const gross = Number(c.gross_pnl || 0);
  return <section className="investments-page">
    <div className="investment-hero hud-panel">
      <div><span className="strategy-eyebrow">WEALTH BUILDING</span><h2>Inversiones</h2><p>JARVIS separa inversión de dinero libre y aumenta el aporte solo cuando tu flujo lo permite.</p>{c.read_only ? <small className={`ibkr-sync-badge ${c.sync_status}`}>IBKR READ-ONLY · {String(p.account_mode || "").toUpperCase()} · {c.sync_status === "live" ? "EN VIVO" : "SIN ACTUALIZAR"} · {p.account_id_masked}</small> : null}</div>
      <button className="strategy-refresh-btn" onClick={load}><RefreshCw size={17}/> Actualizar</button>
    </div>

    <div className="investment-kpi-grid">
      <div className="hud-card"><WalletCards/><span>Valor de cartera</span><strong>{usd(p.market_value)}</strong><small>Patrimonio invertido</small></div>
      <div className="hud-card"><Banknote/><span>{c.read_only ? "Efectivo IBKR" : "Capital aportado"}</span><strong>{usd(c.read_only ? p.cash : p.contributed_capital)}</strong><small>{c.read_only ? `Buying power ${usd(p.buying_power)}` : "Dinero aportado históricamente"}</small></div>
      <div className={`hud-card ${net < 0 ? "negative" : "positive"}`}>{net < 0 ? <TrendingDown/> : <TrendingUp/>}<span>Rentabilidad neta real</span><strong>{usd(net)}</strong><small>{Number(c.return_pct || 0).toFixed(2)}% después de costos</small></div>
      <div className="hud-card"><CircleDollarSign/><span>Reservado para invertir</span><strong>{crc(c.reserved_to_invest_crc)}</strong><small>No cuenta como dinero libre</small></div>
    </div>

    {c.read_only ? <div className="hud-panel ibkr-positions-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">IBKR READ-ONLY</span><h3>Posiciones</h3></div><strong>{positions.length}</strong></div>
      {positions.length ? <div className="allocation-list">{positions.map((position) => <div className="allocation-row ibkr-position-row" key={`${position.symbol}-${position.sec_type}`}><span><b>{position.symbol}</b><small>{position.position} · {position.sec_type} · {position.currency}</small></span><strong>{usd(position.market_value)}<small className={Number(position.unrealized_pnl) < 0 ? "danger-text" : "good-text"}>{usd(position.unrealized_pnl)}</small></strong></div>)}</div> : <p className="muted-text">La cuenta no tiene posiciones abiertas.</p>}
      {p.account_mode === "paper" ? <small className="muted-text">Cuenta paper: se muestra para pruebas, pero no se suma a tu patrimonio real.</small> : null}
    </div> : null}

    <div className="hud-panel investment-plan-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">DIRECTOR FINANCIERO</span><h3>Aporte recomendado</h3></div><strong className="investment-recommendation">{crc(recommended)}</strong></div>
      <p>Meta base actual: <b>{crc(target)}/mes</b>. Si obligaciones, fondo de emergencia o una meta urgente necesitan la caja, JARVIS puede bajar este aporte hasta ₡0.</p>
      <div className="investment-progress"><span style={{width:`${Math.min(100, target ? (Number(c.reserved_to_invest_crc||0)/target)*100 : 0)}%`}} /></div>
    </div>

    <div className="investment-two-col">
      <div className="hud-panel"><h3>Rendimiento</h3><div className="allocation-list">
        <div className="allocation-row"><span>P&L realizado</span><strong>{usd(p.realized_pnl)}</strong></div>
        <div className="allocation-row"><span>P&L no realizado</span><strong>{usd(p.unrealized_pnl)}</strong></div>
        <div className="allocation-row"><span>Dividendos</span><strong>{usd(p.dividends)}</strong></div>
        <div className="allocation-row"><span>Rendimiento bruto</span><strong>{usd(gross)}</strong></div>
      </div></div>
      <div className="hud-panel"><h3>Costos reales</h3><div className="allocation-list">
        <div className="allocation-row"><span>Comisiones IBKR</span><strong>-{usd(p.commissions)}</strong></div>
        <div className="allocation-row"><span>Impuestos</span><strong>-{usd(p.taxes)}</strong></div>
        <div className="allocation-row"><span>Fondeo / Wise</span><strong>-{usd(p.funding_fees)}</strong></div>
        <div className="allocation-row"><span>Resultado neto</span><strong>{usd(net)}</strong></div>
      </div></div>
    </div>

    <div className="hud-panel"><div className="panel-heading"><div><span className="strategy-eyebrow">FONDEO INTELIGENTE</span><h3>Acumular antes de enviar</h3></div><ArrowDownToLine/></div>
      <p>Modelo inicial: Wise ≈ <b>{c.funding_model?.wise_percent_estimate || 1.23}%</b> + <b>${c.funding_model?.wise_to_ibkr_fixed_usd || 1.13}</b> hacia IBKR. JARVIS puede reservar ₡5.000 varios meses y esperar antes de transferir para que el costo fijo pese menos.</p>
      <small className="muted-text">{c.read_only ? "Datos recibidos desde el puente local de solo lectura. JARVIS no puede enviar órdenes." : "IBKR: integración read-only preparada. Hasta conectarla, cartera, comisiones, dividendos e impuestos pueden venir de snapshots/manuales."}</small>
    </div>
  </section>;
}
