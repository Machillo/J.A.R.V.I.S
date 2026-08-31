import {
  AlertTriangle,
  Crown,
  FlaskConical,
  PiggyBank,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  getStrategyBasic,
  getStrategyVip,
  simulateStrategyBasic,
  simulateStrategyVip,
} from "../services/jarvisApi";

const money = (value) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const priorityLabel = {
  income: "Completar ingresos",
  stabilize: "Estabilizar flujo",
  debt: "Acelerar deuda",
  emergency: "Construir seguridad",
};

export default function StrategyBasic({ plan = "basic" }) {
  const vip = plan === "vip";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [extra, setExtra] = useState(25000);
  const [simulation, setSimulation] = useState(null);
  const [loadingSimulation, setLoadingSimulation] = useState(false);
  const [vipScenario, setVipScenario] = useState({
    monthly_income_change: 0,
    monthly_expense_change: 0,
    one_time_extra: 0,
  });

  useEffect(() => {
    setSimulation(null);
    const request = vip ? getStrategyVip() : getStrategyBasic();
    request.then(setData).catch((err) => setError(err.message));
  }, [vip]);

  if (error) return <div className="panel error">{error}</div>;
  if (!data) return <div className="panel">Calculando tu estrategia...</div>;

  const runSimulation = async () => {
    setLoadingSimulation(true);
    setError("");

    try {
      if (vip) {
        const scenario = Object.fromEntries(
          Object.entries(vipScenario).map(([key, value]) => [key, Number(value) || 0]),
        );
        setSimulation(await simulateStrategyVip(scenario));
      } else {
        setSimulation(await simulateStrategyBasic(Number(extra) || 0));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingSimulation(false);
    }
  };

  const allocations = vip ? data.vip_allocations || [] : data.allocations || [];
  const insights = data.insights || {};
  const warnings = vip ? insights.alerts : data.warnings;

  return (
    <section className={`strategy-page plan-view-${plan}`}>
      <div className="hero">
        <span className="strategy-plan-kicker">
          {vip ? (
            <>
              <Crown size={15} /> VIP
            </>
          ) : (
            <>
              <Sparkles size={15} /> BASIC
            </>
          )}
        </span>
        <h1>{vip ? "Dirección financiera VIP" : "Estrategia Basic"}</h1>
        <p>
          {vip
            ? "Finva coordina tus prioridades, deuda, seguridad, metas y margen personal."
            : "Una estrategia matemática construida con tus datos. Si falta información, Finva te lo dice en vez de inventarla."}
        </p>
      </div>

      <div className={`panel strategy strategy-status-${data.status}`}>
        <small>Prioridad actual</small>
        <h2>{priorityLabel[data.priority] || data.priority}</h2>
        <p>{vip ? data.director_note : data.recommendation}</p>
      </div>

      <div className="strategy-metrics">
        <article>
          <small>Ingreso mensual estimado</small>
          <strong>{money(data.monthly_income)}</strong>
        </article>
        <article>
          <small>Gastos esenciales</small>
          <strong>{money(data.essential_expenses)}</strong>
        </article>
        <article>
          <small>Cuotas conocidas</small>
          <strong>{money(data.minimum_debt_payments)}</strong>
        </article>
        <article>
          <small>Margen estratégico</small>
          <strong>{money(data.strategic_margin)}</strong>
        </article>
      </div>

      {vip && (
        <div className="vip-health-grid">
          <article>
            <small>Deuda activa</small>
            <strong>{money(insights.total_debt)}</strong>
          </article>
          <article>
            <small>Metas activas</small>
            <strong>{insights.active_goals ?? 0}</strong>
          </article>
          <article>
            <small>Reserva</small>
            <strong>
              {insights.emergency_progress == null
                ? "Sin objetivo"
                : `${insights.emergency_progress}%`}
            </strong>
          </article>
          <article>
            <small>Meses cubiertos</small>
            <strong>
              {insights.emergency_months == null ? "—" : insights.emergency_months}
            </strong>
          </article>
        </div>
      )}

      {allocations.length > 0 && (
        <div className="panel">
          <div className="strategy-section-title">
            <Target size={18} />
            <h3>{vip ? "Plan recomendado" : "Qué hacer con tu margen"}</h3>
          </div>
          <div className="allocation-list">
            {allocations.map((allocation, index) => (
              <div
                className="allocation-row"
                key={`${allocation.bucket}-${index}`}
              >
                <span>{allocation.label}</span>
                <strong>{money(allocation.amount)}</strong>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.next_paycheck && (
        <div className="panel paycheck-card">
          <div className="strategy-section-title">
            <PiggyBank size={18} />
            <h3>Próximo ingreso</h3>
          </div>
          <p>
            Con tu frecuencia de pago actual, Finva estima{" "}
            {money(data.next_paycheck.estimated_paycheck)} por pago y propone separar:
          </p>
          <div className="allocation-list">
            {data.next_paycheck.envelopes.map((allocation, index) => (
              <div
                className="allocation-row"
                key={`pay-${allocation.bucket}-${index}`}
              >
                <span>{allocation.label}</span>
                <strong>{money(allocation.amount)}</strong>
              </div>
            ))}
          </div>
          {data.next_paycheck.unassigned > 0 && (
            <small>Sin asignar: {money(data.next_paycheck.unassigned)}</small>
          )}
        </div>
      )}

      {!vip && data.projection && (
        <div className="panel projection-card">
          <div className="strategy-section-title">
            <PiggyBank size={18} />
            <h3>Proyección de deuda</h3>
          </div>
          <p>
            Objetivo actual: <b>{data.projection.name}</b>
          </p>
          <p>
            Con el abono recomendado:{" "}
            <b>
              {data.projection.months
                ? `${data.projection.months} meses estimados`
                : "necesitamos más datos"}
            </b>
            .
          </p>
          {data.projection.baseline_months && (
            <small>
              Solo con la cuota registrada serían aproximadamente{" "}
              {data.projection.baseline_months} meses.
            </small>
          )}
        </div>
      )}

      {vip && insights.goal_guidance?.length > 0 && (
        <div className="panel">
          <div className="strategy-section-title">
            <Target size={18} />
            <h3>Metas inteligentes</h3>
          </div>
          <div className="allocation-list">
            {insights.goal_guidance.map((goal) => (
              <div className="smart-goal-row" key={goal.id}>
                <div>
                  <strong>{goal.name}</strong>
                  <small>Faltan {money(goal.remaining)}</small>
                </div>
                <b>
                  {goal.monthly_needed == null
                    ? "Sin fecha"
                    : `${money(goal.monthly_needed)}/mes`}
                </b>
              </div>
            ))}
          </div>
        </div>
      )}

      {!vip && (
        <div className="panel simulator-card">
          <div className="strategy-section-title">
            <FlaskConical size={18} />
            <h3>¿Qué pasa si agrego más?</h3>
          </div>
          <p>Probá un monto mensual adicional sin modificar tus datos.</p>
          <div className="simulator-controls">
            <input
              type="number"
              min="0"
              step="5000"
              value={extra}
              onChange={(event) => setExtra(event.target.value)}
            />
            <button
              type="button"
              onClick={runSimulation}
              disabled={loadingSimulation}
            >
              {loadingSimulation ? "Calculando..." : "Simular"}
            </button>
          </div>
          {simulation && (
            <div className="simulation-result">
              <strong>
                Nuevo margen para estrategia:{" "}
                {money(
                  (simulation.strategic_margin || 0) +
                    (simulation.simulation_extra || 0),
                )}
              </strong>
              {simulation.projection?.months && (
                <span>
                  {simulation.projection.name}: ~{simulation.projection.months} meses
                  con este escenario.
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {vip && (
        <div className="panel simulator-card vip-scenario">
          <div className="strategy-section-title">
            <TrendingUp size={18} />
            <h3>Laboratorio de escenarios</h3>
          </div>
          <p>
            Probá cambios sin tocar tus datos reales. Usá números negativos para una
            reducción mensual.
          </p>
          <div className="vip-scenario-fields">
            <label>
              <span>Cambio ingreso / mes</span>
              <input
                type="number"
                step="10000"
                value={vipScenario.monthly_income_change}
                onChange={(event) =>
                  setVipScenario({
                    ...vipScenario,
                    monthly_income_change: event.target.value,
                  })
                }
              />
            </label>
            <label>
              <span>Cambio gastos / mes</span>
              <input
                type="number"
                step="10000"
                value={vipScenario.monthly_expense_change}
                onChange={(event) =>
                  setVipScenario({
                    ...vipScenario,
                    monthly_expense_change: event.target.value,
                  })
                }
              />
            </label>
            <label>
              <span>Dinero extraordinario</span>
              <input
                type="number"
                min="0"
                step="10000"
                value={vipScenario.one_time_extra}
                onChange={(event) =>
                  setVipScenario({
                    ...vipScenario,
                    one_time_extra: event.target.value,
                  })
                }
              />
            </label>
          </div>
          <button
            className="scenario-button"
            type="button"
            onClick={runSimulation}
            disabled={loadingSimulation}
          >
            {loadingSimulation ? "Calculando..." : "Comparar escenario"}
          </button>
          {simulation?.scenario && (
            <div className="simulation-result">
              <strong>
                {simulation.delta.strategic_margin >= 0 ? "Ganás" : "Perdés"}{" "}
                {money(Math.abs(simulation.delta.strategic_margin))} de margen mensual
              </strong>
              <span>
                Margen actual: {money(simulation.current.strategic_margin)} → escenario:{" "}
                {money(simulation.scenario.strategic_margin)}
              </span>
            </div>
          )}
        </div>
      )}

      {warnings?.length > 0 && (
        <div className="strategy-warnings">
          <div className="strategy-section-title">
            <AlertTriangle size={18} />
            <h3>{vip ? "Alertas del Director" : "Datos que mejorarían la precisión"}</h3>
          </div>
          {warnings.map((warning, index) => (
            <p key={index}>
              {typeof warning === "string" ? warning : warning.message}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
