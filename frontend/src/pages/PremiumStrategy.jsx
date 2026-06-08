import { useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, RefreshCw, Shield, TrendingUp } from "lucide-react";
import { createJarvisPremiumInitialStrategy, getJarvisPremiumStrategyDashboard } from "../services/jarvisApi";

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;

const allocationLabels = {
  ataque_de_deuda: "Ataque de deuda",
  debt_attack: "Ataque de deuda",
  vida_controlada: "Vida controlada",
  controlled_life: "Vida controlada",
  fondo_de_emergencia: "Fondo de emergencia",
  emergency_buffer: "Fondo de emergencia",
  metas_o_inversion: "Metas o inversión",
  goals_or_investment: "Metas o inversión",
};

export default function PremiumStrategy() {
  const [state, setState] = useState({ loading: true, data: null, error: "", running: false });

  const load = async () => {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const data = await getJarvisPremiumStrategyDashboard();
      setState({ loading: false, data, error: "", running: false });
    } catch (error) {
      setState({ loading: false, data: null, error: error.message || "No pude cargar la estrategia.", running: false });
    }
  };

  const runStrategy = async () => {
    setState((current) => ({ ...current, running: true, error: "" }));
    try {
      await createJarvisPremiumInitialStrategy();
      await load();
    } catch (error) {
      setState((current) => ({ ...current, running: false, error: error.message || "No pude ejecutar la estrategia." }));
    }
  };

  useEffect(() => { load(); }, []);

  if (state.loading) {
    return <section className="page premium-strategy-page"><div className="hud-card">Cargando estrategia...</div></section>;
  }

  const payload = state.data || {};
  const strategy = payload.strategy || {};
  const timeline = strategy.timeline || [];
  const allocation = strategy.allocation || {};
  const progress = Math.max(0, Math.min(100, Number(strategy.debt_progress_percent || 0)));

  return (
    <section className="page premium-strategy-page">
      <div className="page-section-header strategy-hero">
        <div>
          <span className="eyebrow">Director Financiero</span>
          <h2>Estrategia Premium</h2>
          <p>Plan activo, progreso de deuda y distribución recomendada. Este panel es el tablero de mando.</p>
        </div>
        <button className="primary-action-button" onClick={runStrategy} disabled={state.running}>
          <RefreshCw size={18} />
          {state.running ? "Ejecutando..." : "Recalcular estrategia"}
        </button>
      </div>

      {state.error && <div className="alert-card"><AlertTriangle size={18} /> {state.error}</div>}

      <div className="strategy-command-card">
        <div className="strategy-title-row">
          <Shield size={24} />
          <div>
            <h3>{payload.title || strategy.title || "Estrategia activa"}</h3>
            <p>{strategy.objective || "Aún no hay objetivo calculado."}</p>
          </div>
        </div>

        <div className="debt-progress-block">
          <div className="progress-label-row">
            <span>Progreso contra deudas</span>
            <strong>{progress.toFixed(1)}%</strong>
          </div>
          <div className="progress-track"><div style={{ width: `${progress}%` }} /></div>
          <small>
            Deuda total actual: {money(strategy.total_debt)} · Base sin extras futuros: {strategy.base_estimated_total_months >= 999 ? "sin cierre" : `${strategy.base_estimated_total_months || "--"} meses`} · Mes actual: {strategy.estimated_total_months >= 999 ? "sin cierre" : `${strategy.estimated_total_months || "--"} meses`}
          </small>
        </div>
      </div>

      <div className="strategy-kpi-grid">
        <div className="hud-card strategy-kpi-card"><span>Ingreso base recurrente</span><strong>{money(strategy.recurring_monthly_income || strategy.monthly_income)}</strong><small>Salario fijo neto sin OT/bonos futuros</small></div>
        <div className="hud-card strategy-kpi-card"><span>Ingreso de este mes</span><strong>{money(strategy.monthly_income)}</strong><small>Base + extras únicos del mes - VGH</small></div>
        <div className="hud-card strategy-kpi-card"><span>Pagos mínimos deuda</span><strong>{money(strategy.monthly_debt_minimums)}</strong><small>Cuotas mensuales normalizadas</small></div>
        <div className="hud-card strategy-kpi-card"><span>Sobrante base</span><strong>{money(strategy.base_estimated_extra_cash)}</strong><small>Recurrente después de Casa y mínimos</small></div>
        <div className="hud-card strategy-kpi-card"><span>Extra único a deuda</span><strong>{money(strategy.current_month_one_time_debt_boost)}</strong><small>OT/bono de este mes aplicado una sola vez</small></div>
        <div className="hud-card strategy-kpi-card"><span>Estado</span><strong>{strategy.status === "critical" ? "Crítico" : "Controlado"}</strong></div>
      </div>

      <div className="hud-panel strategy-scenario-panel">
        <h3>Escenario base vs mes actual</h3>
        <div className="allocation-list">
          <div className="allocation-row"><span>Sin OT/bonos futuros</span><strong>{strategy.base_estimated_total_months >= 999 ? "sin cierre" : `${strategy.base_estimated_total_months || "--"} meses`}</strong></div>
          <div className="allocation-row"><span>Con extras únicos de este mes</span><strong>{strategy.estimated_total_months >= 999 ? "sin cierre" : `${strategy.estimated_total_months || "--"} meses`}</strong></div>
          <div className="allocation-row"><span>Meses adelantados</span><strong>{strategy.months_saved_by_current_extras || 0}</strong></div>
        </div>
      </div>

      <div className="strategy-grid-2">
        <div className="hud-panel">
          <h3><TrendingUp size={18} /> Distribución del dinero</h3>
          <div className="allocation-list">
            {Object.entries(allocation).map(([key, value]) => (
              <div className="allocation-row" key={key}>
                <span>{allocationLabels[key] || key.replaceAll("_", " ")}</span>
                <strong>{value}%</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="hud-panel">
          <h3><CheckCircle2 size={18} /> Reglas del Director</h3>
          <ul className="strategy-rules">
            {(strategy.rules || []).map((rule, index) => <li key={index}>{rule}</li>)}
          </ul>
        </div>
      </div>

      <div className="hud-panel">
        <h3><Activity size={18} /> Ruta de pago</h3>
        <div className="strategy-timeline">
          {timeline.length === 0 && <p className="muted-text">No hay deudas activas para proyectar.</p>}
          {timeline.map((item) => (
            <div className="timeline-item" key={`${item.priority}-${item.name}`}>
              <span className="timeline-rank">#{item.priority}</span>
              <div>
                <strong>{item.name}</strong>
                <p>Saldo {money(item.remaining_amount)} · Pago objetivo {money(item.recommended_payment)} · mínimo {money(item.minimum_payment)}</p>
              </div>
              <b>{item.estimated_months >= 999 ? "sin cierre" : `mes ${item.estimated_months}`}</b>
            </div>
          ))}
        </div>
      </div>

      <div className="hud-panel strategy-content-panel">
        <h3>Guía guardada</h3>
        <pre>{payload.content || "Señor, ejecuta la estrategia premium para guardar una guía."}</pre>
      </div>
    </section>
  );
}
