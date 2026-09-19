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
import { deviceLanguage, localeTag, tx } from "../../lib/locale";

const language = deviceLanguage();
const copy = (es, en) => tx(es, en, language);

const money = (value) =>
  new Intl.NumberFormat(localeTag(language), {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const priorityLabel = {
  income: copy("Completar ingresos", "Complete income details"),
  stabilize: copy("Estabilizar flujo", "Stabilize cash flow"),
  debt: copy("Acelerar deuda", "Accelerate debt payoff"),
  emergency: copy("Construir seguridad", "Build financial security"),
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
  if (!data) return <div className="panel">{copy("Calculando tu estrategia...", "Calculating your strategy...")}</div>;

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
        <h1>{vip ? copy("Dirección financiera VIP", "VIP financial direction") : copy("Estrategia Basic", "Basic strategy")}</h1>
        <p>
          {vip
            ? copy("Finva coordina tus prioridades, deuda, seguridad, metas y margen personal.", "Finva coordinates your priorities, debt, safety, goals, and personal margin.")
            : copy("Una estrategia matemática construida con tus datos. Si falta información, Finva te lo dice en vez de inventarla.", "A mathematical strategy built from your data. If information is missing, Finva tells you instead of making it up.")}
        </p>
      </div>

      <div className={`panel strategy strategy-status-${data.status}`}>
        <small>{copy("Prioridad actual", "Current priority")}</small>
        <h2>{priorityLabel[data.priority] || data.priority}</h2>
        <p>{vip ? data.director_note : data.recommendation}</p>
      </div>

      <div className="strategy-metrics">
        <article>
          <small>{copy("Ingreso mensual estimado", "Estimated monthly income")}</small>
          <strong>{money(data.monthly_income)}</strong>
        </article>
        <article>
          <small>{copy("Gastos esenciales", "Essential expenses")}</small>
          <strong>{money(data.essential_expenses)}</strong>
        </article>
        <article>
          <small>{copy("Cuotas conocidas", "Known payments")}</small>
          <strong>{money(data.minimum_debt_payments)}</strong>
        </article>
        <article>
          <small>{copy("Margen estratégico", "Strategic margin")}</small>
          <strong>{money(data.strategic_margin)}</strong>
        </article>
      </div>

      {vip && (
        <div className="vip-health-grid">
          <article>
            <small>{copy("Deuda activa", "Active debt")}</small>
            <strong>{money(insights.total_debt)}</strong>
          </article>
          <article>
            <small>{copy("Metas activas", "Active goals")}</small>
            <strong>{insights.active_goals ?? 0}</strong>
          </article>
          <article>
            <small>{copy("Reserva", "Reserve")}</small>
            <strong>
              {insights.emergency_progress == null
                ? copy("Sin objetivo", "No target")
                : `${insights.emergency_progress}%`}
            </strong>
          </article>
          <article>
            <small>{copy("Meses cubiertos", "Months covered")}</small>
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
            <h3>{vip ? copy("Plan recomendado", "Recommended plan") : copy("Qué hacer con tu margen", "What to do with your margin")}</h3>
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
            <h3>{copy("Próximo ingreso", "Next income")}</h3>
          </div>
          <p>
            {copy("Con tu frecuencia de pago actual, Finva estima", "With your current pay frequency, Finva estimates")} {money(data.next_paycheck.estimated_paycheck)} {copy("por pago y propone separar:", "per paycheck and suggests setting aside:")}
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
            <small>{copy("Sin asignar", "Unassigned")}: {money(data.next_paycheck.unassigned)}</small>
          )}
        </div>
      )}

      {!vip && data.projection && (
        <div className="panel projection-card">
          <div className="strategy-section-title">
            <PiggyBank size={18} />
            <h3>{copy("Proyección de deuda", "Debt projection")}</h3>
          </div>
          <p>
            {copy("Objetivo actual", "Current target")}: <b>{data.projection.name}</b>
          </p>
          <p>
            {copy("Con el abono recomendado", "With the recommended extra payment")}:{" "}
            <b>
              {data.projection.months
                ? `${data.projection.months} ${copy("meses estimados", "estimated months")}`
                : copy("necesitamos más datos", "we need more data")}
            </b>
            .
          </p>
          {data.projection.baseline_months && (
            <small>
              {copy("Solo con la cuota registrada serían aproximadamente", "With only the recorded payment it would take approximately")} {data.projection.baseline_months} {copy("meses", "months")}.
            </small>
          )}
        </div>
      )}

      {vip && insights.goal_guidance?.length > 0 && (
        <div className="panel">
          <div className="strategy-section-title">
            <Target size={18} />
            <h3>{copy("Metas inteligentes", "Smart goals")}</h3>
          </div>
          <div className="allocation-list">
            {insights.goal_guidance.map((goal) => (
              <div className="smart-goal-row" key={goal.id}>
                <div>
                  <strong>{goal.name}</strong>
                  <small>{copy("Faltan", "Remaining")} {money(goal.remaining)}</small>
                </div>
                <b>
                  {goal.monthly_needed == null
                    ? copy("Sin fecha", "No date")
                    : `${money(goal.monthly_needed)}/${copy("mes", "month")}`}
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
            <h3>{copy("¿Qué pasa si agrego más?", "What if I add more?")}</h3>
          </div>
          <p>{copy("Probá un monto mensual adicional sin modificar tus datos.", "Try an additional monthly amount without changing your data.")}</p>
          <div className="simulator-controls">
            <input
              type="number"
              min="0"
              step="0.01"
              value={extra}
              onChange={(event) => setExtra(event.target.value)}
            />
            <button
              className="finva-button finva-button-secondary"
              type="button"
              onClick={runSimulation}
              disabled={loadingSimulation}
            >
              {loadingSimulation ? copy("Calculando...", "Calculating...") : copy("Simular", "Simulate")}
            </button>
          </div>
          {simulation && (
            <div className="simulation-result">
              <strong>
                {copy("Nuevo margen para estrategia", "New strategy margin")}:{" "}
                {money(
                  (simulation.strategic_margin || 0) +
                    (simulation.simulation_extra || 0),
                )}
              </strong>
              {simulation.projection?.months && (
                <span>
                  {simulation.projection.name}: ~{simulation.projection.months}{" "}
                  {copy("meses con este escenario.", "months with this scenario.")}
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
            <h3>{copy("Laboratorio de escenarios", "Scenario lab")}</h3>
          </div>
          <p>
            {copy("Probá cambios sin tocar tus datos reales. Usá números negativos para una reducción mensual.", "Try changes without touching your real data. Use negative numbers for a monthly reduction.")}
          </p>
          <div className="vip-scenario-fields">
            <label>
              <span>{copy("Cambio ingreso / mes", "Income change / month")}</span>
              <input
                type="number"
                step="0.01"
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
              <span>{copy("Cambio gastos / mes", "Expense change / month")}</span>
              <input
                type="number"
                step="0.01"
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
              <span>{copy("Dinero extraordinario", "One-time money")}</span>
              <input
                type="number"
                min="0"
                step="0.01"
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
            className="scenario-button finva-button finva-button-primary"
            type="button"
            onClick={runSimulation}
            disabled={loadingSimulation}
          >
            {loadingSimulation ? copy("Calculando...", "Calculating...") : copy("Comparar escenario", "Compare scenario")}
          </button>
          {simulation?.scenario && (
            <div className="simulation-result">
              <strong>
                {simulation.delta.strategic_margin >= 0 ? copy("Ganás", "You gain") : copy("Perdés", "You lose")} {money(Math.abs(simulation.delta.strategic_margin))} {copy("de margen mensual", "in monthly margin")}
              </strong>
              <span>
                {copy("Margen actual", "Current margin")}: {money(simulation.current.strategic_margin)} → {copy("escenario", "scenario")}:{" "}
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
            <h3>{vip ? copy("Alertas del Director", "Director alerts") : copy("Datos que mejorarían la precisión", "Data that would improve accuracy")}</h3>
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
