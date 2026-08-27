import { useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, RefreshCw, Shield, TrendingUp } from "lucide-react";
import { getDebtAdvisory, getJarvisPremiumStrategyDashboard } from "../services/jarvisApi";

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;
const usd = (value) => `$${Number(value || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const allocationLabels = {
  ataque_de_deuda: "Ataque de deuda",
  debt_attack: "Ataque de deuda",
  vida_controlada: "Vida controlada",
  controlled_life: "Vida controlada",
  fondo_de_emergencia: "Fondo de emergencia",
  emergency_buffer: "Fondo de emergencia",
  metas_o_inversion: "Metas o inversión",
  goals_or_investment: "Metas o inversión",
  meta_prioritaria: "Meta prioritaria",
  inversion: "Inversión",
};

export default function PremiumStrategy() {
  const [state, setState] = useState({ loading: true, data: null, debtAdvice: null, error: "", running: false });

  const load = async () => {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const [strategyResult, debtAdviceResult] = await Promise.allSettled([
        getJarvisPremiumStrategyDashboard(),
        getDebtAdvisory(),
      ]);

      if (strategyResult.status === "rejected") {
        throw strategyResult.reason;
      }

      setState({
        loading: false,
        data: strategyResult.value,
        debtAdvice: debtAdviceResult.status === "fulfilled" ? debtAdviceResult.value : null,
        error: "",
        running: false,
      });
    } catch (error) {
      setState({ loading: false, data: null, debtAdvice: null, error: error.message || "No pude cargar la estrategia.", running: false });
    }
  };

  const runStrategy = async () => {
    setState((current) => ({ ...current, running: true, error: "" }));
    try {
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
  const debtAdvice = state.debtAdvice || {};
  const debtScenarioList = Array.isArray(debtAdvice.scenarios) ? debtAdvice.scenarios : [];
  const primaryDebtScenario = debtScenarioList[0] || {};
  const debtScenarios = Array.isArray(debtAdvice.scenarios)
    ? primaryDebtScenario
    : (debtAdvice.scenarios || debtAdvice.options || {});
  const timeline = strategy.timeline || [];
  const allocation = strategy.allocation || {};
  const allocationAmounts = strategy.allocation_amounts || {};
  const allocationItems = Array.isArray(strategy.allocation_items)
    ? strategy.allocation_items
    : Object.entries(allocation).map(([key, percentage]) => ({
        key,
        percentage,
        amount: allocationAmounts[key] || 0,
      }));
  const allocationBase = Number(strategy.allocation_base_amount || strategy.monthly_income || 0);
  const progress = Math.max(0, Math.min(100, Number(strategy.debt_progress_percent || 0)));
  const emergency = strategy.emergency_fund || {};
  const urgentGoals = Array.isArray(strategy.urgent_goals) ? strategy.urgent_goals : [];
  const investments = strategy.investment_portfolio || {};
  const emergencyProgress = Math.max(
    0,
    Math.min(
      100,
      Number(emergency.next_target || 0) > 0
        ? (Number(emergency.current || 0) / Number(emergency.next_target || 1)) * 100
        : 0
    )
  );

  return (
    <section className="page premium-strategy-page">
      <div className="page-section-header strategy-hero">
        <div>
          <span className="eyebrow">Director Financiero</span>
          <h2>Strategy</h2>
          <p>Prioridades dinámicas: obligaciones, metas con fecha, seguridad, deuda y dinero libre para vivir.</p>
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
            <div className="strategy-mode-line">
              <h3>{payload.title || strategy.title || "Estrategia activa"}</h3>
              {strategy.mode_label && <span className={`strategy-mode-badge mode-${strategy.mode || "default"}`}>{strategy.mode_label}</span>}
            </div>
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
        <div className="hud-card strategy-kpi-card">
          <span>Ingreso del ciclo</span>
          <strong>{money(strategy.monthly_income)}</strong>
          <small>Ingreso real esperado del ciclo actual</small>
        </div>
        <div className="hud-card strategy-kpi-card">
          <span>Disponible para repartir</span>
          <strong>{money(strategy.allocation_base_amount)}</strong>
          <small>Después de gastos y pagos del ciclo</small>
        </div>
        <div className="hud-card strategy-kpi-card strategy-safe-card">
          <span>Seguro para gastar</span>
          <strong>{money(strategy.safe_to_spend)}</strong>
          <small>Vida controlada sin tocar metas, seguridad o deuda</small>
        </div>
        <div className="hud-card strategy-kpi-card">
          <span>Fondo de emergencia</span>
          <strong>{money(emergency.current)}</strong>
          <small>Siguiente objetivo: {money(emergency.next_target)}</small>
        </div>
        <div className="hud-card strategy-kpi-card">
          <span>Meta prioritaria</span>
          <strong>{money(strategy.current_goal_allocation)}</strong>
          <small>{urgentGoals[0]?.name ? `${urgentGoals[0].name} · reserva de este ciclo` : "Sin meta urgente este ciclo"}</small>
        </div>
        <div className="hud-card strategy-kpi-card strategy-investment-card">
          <span>Inversión recomendada</span>
          <strong>{money(strategy.investment_recommended)}</strong>
          <small>Meta base: {money(strategy.investment_target || 5000)} · solo si el flujo lo permite</small>
        </div>
        <div className="hud-card strategy-kpi-card">
          <span>Ataque extra a deuda</span>
          <strong>{money(strategy.current_month_one_time_debt_boost)}</strong>
          <small>Solo excedente; no sustituye cuotas normales</small>
        </div>
        <div className="hud-card strategy-kpi-card">
          <span>Deuda total</span>
          <strong>{money(strategy.total_debt)}</strong>
          <small>Progreso pagado: {progress.toFixed(1)}%</small>
        </div>
        <div className="hud-card strategy-kpi-card">
          <span>Estado</span>
          <strong>{strategy.status === "critical" ? "Crítico" : strategy.status === "strong" ? "Fuerte" : "Controlado"}</strong>
          <small>{strategy.mode_label || "Director dinámico"}</small>
        </div>
      </div>

      <div className="strategy-grid-2">
        <div className="hud-panel strategy-safety-panel">
          <h3><Shield size={18} /> Seguridad financiera</h3>
          <div className="progress-label-row">
            <span>Fondo actual → siguiente nivel</span>
            <strong>{emergencyProgress.toFixed(0)}%</strong>
          </div>
          <div className="progress-track"><div style={{ width: `${emergencyProgress}%` }} /></div>
          <div className="allocation-list strategy-safety-list">
            <div className="allocation-row"><span>Mini-colchón</span><strong>{money(emergency.mini_target)}</strong></div>
            <div className="allocation-row"><span>1 mes esencial</span><strong>{money(emergency.one_month_target)}</strong></div>
            <div className="allocation-row"><span>3 meses esenciales</span><strong>{money(emergency.three_month_target)}</strong></div>
          </div>
          <p className="panel-subtitle">Faltan {money(emergency.gap_to_next_target)} para el siguiente nivel de seguridad.</p>
        </div>

        <div className="hud-panel strategy-priority-panel">
          <h3><Activity size={18} /> Prioridad actual</h3>
          <strong className="strategy-priority-mode">{strategy.mode_label || "DIRECTOR DINÁMICO"}</strong>
          <p>{strategy.mode_reason || strategy.objective}</p>
          {urgentGoals.length > 0 && (
            <div className="strategy-goal-focus">
              <span>Meta protegida</span>
              <strong>{urgentGoals[0].name}</strong>
              <small>Faltan {money(urgentGoals[0].remaining_amount)} · {urgentGoals[0].months_left} mes(es)</small>
            </div>
          )}
        </div>
      </div>

      <div className="hud-panel strategy-investments-panel">
        <h3><TrendingUp size={18} /> Inversiones · quinta capa</h3>
        <p className="panel-subtitle">JARVIS separa inversión de ahorro y de dinero libre. Por ahora el registro es local; queda preparado para sincronización IBKR solo lectura.</p>
        <div className="investment-metrics-grid">
          <div><span>Valor de cartera</span><strong>{usd(investments.market_value)}</strong></div>
          <div><span>Capital aportado</span><strong>{usd(investments.contributed_capital)}</strong></div>
          <div><span>P&L neto</span><strong>{usd(investments.net_pnl)}</strong></div>
          <div><span>Reservado para invertir</span><strong>{money(investments.reserved_to_invest_crc)}</strong></div>
        </div>
        <div className="allocation-list strategy-investment-costs">
          <div className="allocation-row"><span>Dividendos</span><strong>{usd(investments.dividends)}</strong></div>
          <div className="allocation-row"><span>Comisiones</span><strong>-{usd(investments.commissions)}</strong></div>
          <div className="allocation-row"><span>Impuestos</span><strong>-{usd(investments.taxes)}</strong></div>
          <div className="allocation-row"><span>Costos de fondeo</span><strong>-{usd(investments.funding_fees)}</strong></div>
        </div>
        <small className="muted-text">Modelo de fondeo inicial: Wise ≈ {investments.funding_model?.wise_percent_estimate || 1.23}% + ${investments.funding_model?.wise_to_ibkr_fixed_usd || 1.13} hacia IBKR. JARVIS puede acumular aportes pequeños antes de transferir.</small>
      </div>

      <div className="hud-panel strategy-scenario-panel">
        <h3>Escenario base vs mes actual</h3>
        <div className="allocation-list">
          <div className="allocation-row"><span>Sin OT/bonos futuros</span><strong>{strategy.base_estimated_total_months >= 999 ? "sin cierre" : `${strategy.base_estimated_total_months || "--"} meses`}</strong></div>
          <div className="allocation-row"><span>Con extras únicos de este mes</span><strong>{strategy.estimated_total_months >= 999 ? "sin cierre" : `${strategy.estimated_total_months || "--"} meses`}</strong></div>
          <div className="allocation-row"><span>Meses adelantados</span><strong>{strategy.months_saved_by_current_extras || 0}</strong></div>
        </div>
      </div>


      <div className="hud-panel strategy-debt-advice-panel">
        <h3>Asesoría de deuda</h3>
        <p className="strategy-advice-line">
          {debtAdvice.message || "Señor, registre deudas activas para comparar amortización, ahorro y estrategia híbrida."}
        </p>
        <div className="debt-advice-scenarios">
          <div>
            <span>A) Abonar mensualmente</span>
            <strong>{money(debtScenarios.A_monthly_amortization?.payment || debtScenarios.monthly_amortization?.monthly_payment || debtScenarios.amortization?.monthly_payment || 0)}</strong>
            <small>{debtScenarios.A_monthly_amortization?.months || debtScenarios.monthly_amortization?.estimated_months || debtScenarios.amortization?.estimated_months || "--"} meses</small>
          </div>
          <div>
            <span>B) Ahorrar y liquidar</span>
            <strong>{money(debtScenarios.B_save_and_liquidate?.monthly_saving || debtScenarios.save_then_pay?.target_amount || debtScenarios.lump_sum?.target_amount || 0)}</strong>
            <small>{debtScenarios.B_save_and_liquidate?.estimated_months_to_lump_sum || debtScenarios.save_then_pay?.estimated_months || debtScenarios.lump_sum?.estimated_months || "--"} meses</small>
          </div>
          <div>
            <span>C) Estrategia híbrida</span>
            <strong>{money(debtScenarios.C_hybrid?.payment || debtScenarios.hybrid?.monthly_payment || debtScenarios.hybrid?.recommended_payment || 0)}</strong>
            <small>{debtScenarios.C_hybrid?.months || debtScenarios.hybrid?.estimated_months || "--"} meses</small>
          </div>
        </div>
      </div>

      <div className="strategy-grid-2">
        <div className="hud-panel">
          <h3><TrendingUp size={18} /> Distribución del dinero</h3>
          <p className="panel-subtitle">Excedente real del ciclo: {money(allocationBase)}. Los porcentajes cambian automáticamente según prioridad y seguridad.</p>
          <div className="allocation-list">
            {allocationItems.map((item) => {
              const key = item.key;
              const percent = Number(item.percentage ?? allocation[key] ?? 0);
              const amount = Number(item.amount ?? allocationAmounts[key] ?? 0);
              return (
                <div className="allocation-row allocation-row-amount" key={key}>
                  <span>{allocationLabels[key] || key.replaceAll("_", " ")}</span>
                  <strong>{percent}% <b>{money(amount)}</b></strong>
                </div>
              );
            })}
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
                <p>Saldo {money(item.remaining_amount)} · Pago objetivo {money(item.recommended_payment)} · pago base {money(item.minimum_payment)}</p>
              </div>
              <b>{item.estimated_months >= 999 ? "sin cierre" : `mes ${item.estimated_months}`}</b>
            </div>
          ))}
        </div>
      </div>

    </section>
  );
}
