import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  LifeBuoy,
  RefreshCw,
  Save,
  Shield,
  TrendingUp,
} from "lucide-react";
import {
  getDebtAdvisory,
  getJarvisPremiumStrategyDashboard,
  getSalvavidas,
  updateSalvavidas,
} from "../services/jarvisApi";

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;

const allocationLabels = {
  ataque_de_deuda: "Ataque extra a deuda",
  debt_attack: "Ataque extra a deuda",
  vida_controlada: "Libre para usar",
  controlled_life: "Libre para usar",
  fondo_de_emergencia: "Salvavidas",
  emergency_buffer: "Salvavidas",
  metas_o_inversion: "Metas / patrimonio",
  goals_or_investment: "Metas / patrimonio",
  meta_prioritaria: "Meta prioritaria",
  inversion: "Inversión",
};

const debtTypeLabels = {
  tasa_cero: "Tasa cero",
  minicuotas: "Minicuotas",
  compra_financiada: "Compra financiada",
  credit_card: "Tarjeta",
  tarjeta: "Tarjeta",
  personal_loan: "Préstamo",
  loan: "Préstamo",
  familiar: "Familiar",
  other: "Deuda",
};

const formatDate = (value) => {
  if (!value) return "Sin fecha estimada";
  const parsed = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return "Sin fecha estimada";
  return new Intl.DateTimeFormat("es-CR", { month: "long", year: "numeric" }).format(parsed);
};

const monthsText = (value) => {
  const months = Number(value || 0);
  if (!months) return "--";
  if (months >= 999) return "Revisar cuota";
  return `${months} ${months === 1 ? "mes" : "meses"}`;
};

const optionCopy = {
  salvavidas: {
    title: "Salvavidas",
    subtitle: "Definí y construí tus 6 meses de cobertura.",
    icon: LifeBuoy,
  },
  investments: {
    title: "Inversiones",
    subtitle: "Mirá cuánto podés invertir sin tocar obligaciones.",
    icon: TrendingUp,
  },
  debts: {
    title: "Asesoría de deudas",
    subtitle: "Analizá prioridad, impacto y ruta de salida.",
    icon: Activity,
  },
  distribution: {
    title: "Distribución de dinero",
    subtitle: "Repartí únicamente el sobrante real del ciclo.",
    icon: CircleDollarSign,
  },
};

export default function PremiumStrategy() {
  const [state, setState] = useState({ loading: true, data: null, debtAdvice: null, error: "", running: false });
  const [activeSection, setActiveSection] = useState(null);
  const [salvavidasState, setSalvavidasState] = useState({ loading: true, saving: false, data: null, error: "" });
  const [salvavidasAmount, setSalvavidasAmount] = useState("");
  const [protectedExpenseIds, setProtectedExpenseIds] = useState([]);

  const load = async ({ keepPage = false } = {}) => {
    setState((current) => ({ ...current, loading: keepPage ? current.loading : true, running: keepPage, error: "" }));
    try {
      const strategyResult = await getJarvisPremiumStrategyDashboard();
      const strategyPayload = strategyResult?.strategy || {};
      let debtAdvice = null;
      try {
        debtAdvice = await getDebtAdvisory(Number(strategyPayload.debt_attack_extra || 0));
      } catch {
        debtAdvice = null;
      }
      setState({ loading: false, data: strategyResult, debtAdvice, error: "", running: false });
      return strategyResult;
    } catch (error) {
      setState((current) => ({
        loading: false,
        data: current.data,
        debtAdvice: current.debtAdvice,
        error: error.message || "No pude cargar la estrategia.",
        running: false,
      }));
      return null;
    }
  };

  const runStrategy = async () => {
    await Promise.all([load({ keepPage: true }), loadSalvavidas()]);
  };

  const loadSalvavidas = async () => {
    setSalvavidasState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const data = await getSalvavidas();
      setSalvavidasState({ loading: false, saving: false, data, error: "" });
      setSalvavidasAmount(String(Number(data?.current_amount || 0)));
      setProtectedExpenseIds(Array.isArray(data?.protected_expense_ids) ? data.protected_expense_ids : []);
      return data;
    } catch (error) {
      setSalvavidasState({ loading: false, saving: false, data: null, error: error.message || "No pude cargar el Salvavidas." });
      return null;
    }
  };

  const saveSalvavidas = async () => {
    const amount = Number(salvavidasAmount || 0);
    if (!Number.isFinite(amount) || amount < 0) {
      setSalvavidasState((current) => ({ ...current, error: "El saldo del Salvavidas debe ser un monto válido mayor o igual a cero." }));
      return;
    }
    setSalvavidasState((current) => ({ ...current, saving: true, error: "" }));
    try {
      const data = await updateSalvavidas({
        current_amount: amount,
        protected_expense_ids: protectedExpenseIds,
      });
      setSalvavidasState({ loading: false, saving: false, data, error: "" });
      setSalvavidasAmount(String(Number(data?.current_amount || 0)));
      setProtectedExpenseIds(Array.isArray(data?.protected_expense_ids) ? data.protected_expense_ids : []);
      await load({ keepPage: true });
    } catch (error) {
      setSalvavidasState((current) => ({ ...current, saving: false, error: error.message || "No pude guardar el Salvavidas." }));
    }
  };

  const toggleProtectedExpense = (expenseId) => {
    setProtectedExpenseIds((current) =>
      current.includes(expenseId) ? current.filter((id) => id !== expenseId) : [...current, expenseId]
    );
  };

  useEffect(() => {
    load();
    loadSalvavidas();
  }, []);

  const payload = state.data || {};
  const strategy = payload.strategy || {};
  const priority = strategy.priority || {};
  const timeline = useMemo(
    () => (Array.isArray(strategy.timeline) ? strategy.timeline : []),
    [strategy.timeline]
  );
  const allocation = strategy.allocation || {};
  const allocationAmounts = strategy.allocation_amounts || {};
  const allocationItems = Array.isArray(strategy.allocation_items)
    ? strategy.allocation_items
    : Object.entries(allocation).map(([key, percentage]) => ({ key, percentage, amount: allocationAmounts[key] || 0 }));
  const allocationBase = Number(strategy.allocation_base_amount || 0);
  const allocationTotal = Number(strategy.allocation_total || allocationItems.reduce((sum, item) => sum + Number(item.amount || 0), 0));
  const progress = Math.max(0, Math.min(100, Number(strategy.debt_progress_percent || 0)));
  const debtAdvice = state.debtAdvice || {};
  const adviceScenarios = useMemo(
    () => (Array.isArray(debtAdvice.scenarios) ? debtAdvice.scenarios : []),
    [debtAdvice.scenarios]
  );

  const salvavidas = salvavidasState.data || {};
  const salvavidasProgress = Math.max(0, Math.min(100, Number(salvavidas.progress_percent || 0)));
  const salvavidasExpenses = Array.isArray(salvavidas.available_expenses) ? salvavidas.available_expenses : [];
  const salvavidasDebts = Array.isArray(salvavidas.debts) ? salvavidas.debts : [];
  const mandatoryExpenses = Array.isArray(salvavidas.mandatory_expenses) ? salvavidas.mandatory_expenses : [];
  const salvavidasMilestones = Array.isArray(salvavidas.milestones) ? salvavidas.milestones : [];

  const rankedAdvice = useMemo(() => {
    const byId = new Map(timeline.map((item, index) => [String(item.id ?? item.name), index]));
    return [...adviceScenarios].sort((a, b) => {
      const aDebt = a?.debt || {};
      const bDebt = b?.debt || {};
      const aRank = byId.get(String(aDebt.id ?? aDebt.name)) ?? 999;
      const bRank = byId.get(String(bDebt.id ?? bDebt.name)) ?? 999;
      return aRank - bRank;
    });
  }, [adviceScenarios, timeline]);

  if (state.loading && !state.data) {
    return <section className="page premium-strategy-page"><div className="hud-card">Cargando estrategia...</div></section>;
  }

  const investmentRecommended = Number(strategy.investment_recommended || 0);
  const investmentState = allocationBase <= 0 ? "blocked" : investmentRecommended > 0 ? "ready" : "limited";
  const formula = strategy.distribution_formula || {};
  const distributionBalanced = Math.abs(allocationBase - allocationTotal) <= 1;

  const renderSalvavidas = () => (
    <div className="strategy-detail-panel salvavidas-panel strategy-v3-detail">
      <div className="strategy-detail-heading">
        <div className="strategy-title-row">
          <LifeBuoy size={22} />
          <div>
            <h3>Salvavidas · 6 meses</h3>
            <p>Deudas, Casa y Línea entran solas. Vos elegís qué otros gastos querés proteger.</p>
          </div>
        </div>
        <span className="salvavidas-mode-badge">SALDO MANUAL</span>
      </div>

      {salvavidasState.error && <div className="alert-card"><AlertTriangle size={18} /> {salvavidasState.error}</div>}

      {salvavidasState.loading ? (
        <div className="salvavidas-loading">Calculando tu cobertura...</div>
      ) : (
        <>
          <div className="salvavidas-summary-grid">
            <div><span>Objetivo 6 meses</span><strong>{money(salvavidas.target_amount)}</strong></div>
            <div><span>Guardado</span><strong>{money(salvavidas.current_amount)}</strong></div>
            <div><span>Faltante</span><strong>{money(salvavidas.missing_amount)}</strong></div>
            <div><span>Cobertura</span><strong>{Number(salvavidas.coverage_months || 0).toFixed(1)} meses</strong></div>
          </div>

          <div className="salvavidas-progress-block">
            <div className="progress-label-row"><span>Camino a 6 meses</span><strong>{salvavidasProgress.toFixed(0)}%</strong></div>
            <div className="progress-track"><div style={{ width: `${salvavidasProgress}%` }} /></div>
            <div className="salvavidas-milestones">
              {salvavidasMilestones.map((item) => (
                <div key={item.months} className={`salvavidas-milestone ${item.reached ? "reached" : ""}`}>
                  {item.reached ? <CheckCircle2 size={16} /> : <span className="milestone-dot" />}
                  <span>{item.months} {item.months === 1 ? "mes" : "meses"}</span>
                  <strong>{money(item.target)}</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="salvavidas-editor">
            <label className="salvavidas-amount-field">
              <span>¿Cuánto tenés guardado hoy?</span>
              <div className="salvavidas-money-input">
                <span>₡</span>
                <input
                  type="number"
                  min="0"
                  step="1000"
                  inputMode="decimal"
                  value={salvavidasAmount}
                  onChange={(event) => setSalvavidasAmount(event.target.value)}
                  aria-label="Saldo actual del Salvavidas"
                />
              </div>
            </label>

            <div className="strategy-v3-subsection">
              <div className="salvavidas-section-copy">
                <strong>Obligaciones automáticas</strong>
                <small>No se pueden desmarcar y no vuelven a aparecer como gastos opcionales.</small>
              </div>

              <div className="salvavidas-component-row locked">
                <div><span>Deudas activas</span><small>Incluye préstamos, Tasa Cero y Minicuotas mientras tengan saldo.</small></div>
                <strong>{money(salvavidas.components?.debt_monthly_payments)}</strong>
              </div>
              {salvavidasDebts.length > 0 && (
                <div className="salvavidas-debt-list">
                  {salvavidasDebts.map((debt) => (
                    <div key={debt.id}>
                      <span>{debt.name} <small>· {debtTypeLabels[debt.debt_type] || debt.debt_type || "Deuda"}</small></span>
                      <strong>{money(debt.monthly_payment)}/mes</strong>
                    </div>
                  ))}
                </div>
              )}

              <div className="salvavidas-component-row locked">
                <div><span>Casa + Línea</span><small>Pagos recurrentes que JARVIS protege siempre.</small></div>
                <strong>{money(salvavidas.components?.mandatory_fixed_expenses)}</strong>
              </div>
              {mandatoryExpenses.length > 0 && (
                <div className="salvavidas-debt-list">
                  {mandatoryExpenses.map((expense) => (
                    <div key={expense.id}><span>{expense.name}</span><strong>{money(expense.monthly_amount)}/mes</strong></div>
                  ))}
                </div>
              )}
            </div>

            <div className="salvavidas-expense-section">
              <div className="salvavidas-section-copy">
                <strong>Otros gastos que querés proteger</strong>
                <small>Gym, Muay Thai, suscripciones u otros recurrentes: vos decidís.</small>
              </div>
              {salvavidasExpenses.length === 0 ? (
                <p className="muted-text">No hay otros gastos fijos activos para seleccionar.</p>
              ) : (
                <div className="salvavidas-expense-list">
                  {salvavidasExpenses.map((expense) => {
                    const checked = protectedExpenseIds.includes(expense.id);
                    return (
                      <label key={expense.id} className={`salvavidas-expense-option ${checked ? "selected" : ""}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleProtectedExpense(expense.id)} />
                        <span className="salvavidas-check">{checked ? <CheckCircle2 size={18} /> : null}</span>
                        <span className="salvavidas-expense-copy"><strong>{expense.name}</strong><small>{expense.category}</small></span>
                        <strong>{money(expense.monthly_amount)}/mes</strong>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="salvavidas-base-total"><span>Costo mensual protegido</span><strong>{money(salvavidas.monthly_base)}</strong></div>

            <button className="primary-action-button salvavidas-save" type="button" onClick={saveSalvavidas} disabled={salvavidasState.saving}>
              <Save size={18} />
              {salvavidasState.saving ? "Guardando..." : "Guardar Salvavidas"}
            </button>
            <small className="salvavidas-verification-note">{salvavidas.verification?.message}</small>
          </div>
        </>
      )}
    </div>
  );

  const renderInvestments = () => (
    <div className="strategy-detail-panel strategy-v3-detail strategy-investment-decision">
      <div className="strategy-detail-heading">
        <div className="strategy-title-row"><TrendingUp size={22} /><div><h3>Inversiones</h3><p>Acá solo importa cuánto podés invertir sin tocar dinero comprometido.</p></div></div>
      </div>
      <div className={`strategy-investment-decision-card ${investmentState}`}>
        <span>{investmentState === "ready" ? "PODÉS INVERTIR" : investmentState === "blocked" ? "NO INVERTIR ESTE CICLO" : "MANTENER INVERSIÓN EN PAUSA"}</span>
        <strong>{money(investmentRecommended)}</strong>
        <p>
          {investmentRecommended > 0
            ? `Sale únicamente del sobrante real de ${money(allocationBase)} después de gastos y obligaciones.`
            : allocationBase <= 0
              ? "No hay sobrante real después de cubrir lo registrado y lo obligatorio."
              : "Hay sobrante, pero la estrategia actual lo necesita antes en otra prioridad."}
        </p>
      </div>
      <div className="strategy-v3-note">
        <Shield size={17} />
        <span>Saldo IBKR, rendimiento y posiciones siguen viviendo en Patrimonio/Inversiones; Strategy no los duplica.</span>
      </div>
    </div>
  );

  const renderDebtAdvice = () => (
    <div className="strategy-detail-panel strategy-v3-detail">
      <div className="strategy-detail-heading">
        <div className="strategy-title-row"><Activity size={22} /><div><h3>Asesoría de deudas</h3><p>Qué atacar, cuánto cambia el tiempo y qué ruta sigue cada deuda activa.</p></div></div>
      </div>

      <div className="strategy-debt-advice-summary">
        <span>Extra asignado a deuda este ciclo</span>
        <strong>{money(strategy.debt_attack_extra)}</strong>
        <small>{debtAdvice.message || "JARVIS recalcula la prioridad con tus datos activos."}</small>
      </div>

      {rankedAdvice.length === 0 ? (
        <p className="muted-text">No hay deudas activas para analizar.</p>
      ) : (
        <div className="strategy-debt-analysis-list">
          {rankedAdvice.map((scenario, index) => {
            const debt = scenario.debt || {};
            const baseline = scenario.baseline_minimum || {};
            const amortization = scenario.A_monthly_amortization || {};
            const save = scenario.B_save_and_liquidate || {};
            const hybrid = scenario.C_hybrid || {};
            const recommended = scenario.recommended_scenario || "";
            return (
              <article className="strategy-debt-analysis-card" key={debt.id || `${debt.name}-${index}`}>
                <header>
                  <span className="timeline-rank">#{index + 1}</span>
                  <div><h4>{debt.name || "Deuda"}</h4><small>{debtTypeLabels[debt.debt_type] || String(debt.debt_type || "Deuda").replaceAll("_", " ")}</small></div>
                  <strong>{money(debt.remaining_amount)}</strong>
                </header>

                <div className="strategy-debt-mini-grid">
                  <div><span>Cuota</span><strong>{money(debt.monthly_payment)}</strong></div>
                  <div><span>Tasa</span><strong>{Number(debt.interest_rate || 0).toFixed(2)}%</strong></div>
                  <div><span>Solo mínimos</span><strong>{monthsText(baseline.months)}</strong></div>
                </div>

                <p className="strategy-advice-line">{scenario.recommendation}</p>

                <div className="strategy-debt-options-v3">
                  <div className={recommended === "MINIMUM" ? "recommended" : ""}>
                    <span>Mantener mínimo</span><strong>{money(debt.monthly_payment)}</strong><small>{monthsText(baseline.months)}</small>
                  </div>
                  <div className={recommended === "A" ? "recommended" : ""}>
                    <span>Abono mensual</span><strong>{money(amortization.payment)}</strong><small>{monthsText(amortization.months)}{amortization.months_saved_vs_minimum ? ` · ahorra ${amortization.months_saved_vs_minimum} mes(es)` : ""}</small>
                  </div>
                  <div className={recommended === "B" ? "recommended" : ""}>
                    <span>Ahorrar y liquidar</span><strong>{money(save.monthly_saving)}</strong><small>{save.estimated_months_to_lump_sum ? `${save.estimated_months_to_lump_sum} mes(es) para acumular` : "Sin sobrante"}</small>
                  </div>
                  <div className={recommended === "C" ? "recommended" : ""}>
                    <span>Híbrida</span><strong>{money(hybrid.payment)}</strong><small>{monthsText(hybrid.months)}{hybrid.months_saved_vs_minimum ? ` · ahorra ${hybrid.months_saved_vs_minimum} mes(es)` : ""}</small>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <div className="strategy-route-v3">
        <div className="salvavidas-section-copy"><strong>Ruta de pago activa</strong><small>Las deudas pagadas o canceladas desaparecen; no quedan como “sin cierre”.</small></div>
        {timeline.length === 0 ? (
          <p className="muted-text">No hay deudas activas para proyectar.</p>
        ) : (
          <div className="strategy-timeline">
            {timeline.map((item) => (
              <div className="timeline-item strategy-route-item" key={item.id || `${item.priority}-${item.name}`}>
                <span className="timeline-rank">#{item.priority}</span>
                <div><strong>{item.name}</strong><p>Saldo {money(item.remaining_amount)} · objetivo {money(item.recommended_payment)}/mes</p></div>
                <b>{item.estimated_payoff_date ? formatDate(item.estimated_payoff_date) : "Revisar cuota"}</b>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const renderDistribution = () => (
    <div className="strategy-detail-panel strategy-v3-detail strategy-distribution-v3">
      <div className="strategy-detail-heading">
        <div className="strategy-title-row"><CircleDollarSign size={22} /><div><h3>Distribución de dinero</h3><p>JARVIS reparte solo lo que verdaderamente sobró después de pagos y gastos conocidos.</p></div></div>
      </div>

      <div className="strategy-surplus-card">
        <span>SOBRANTE REAL PARA REPARTIR</span>
        <strong>{money(allocationBase)}</strong>
        <small>{Number(strategy.new_expenses_after_cut_count || 0) > 0 ? `${strategy.new_expenses_after_cut_count} gasto(s) nuevo(s) ya redujeron este monto.` : "Se recalcula cuando aparece un nuevo gasto."}</small>
      </div>

      <div className="strategy-distribution-formula">
        <div><span>Ingreso del ciclo</span><strong>+ {money(formula.income)}</strong></div>
        <div><span>Gastos del estado/corte</span><strong>- {money(formula.statement_spending)}</strong></div>
        <div><span>Nuevos gastos desde el corte</span><strong>- {money(formula.new_spending_after_cut)}</strong></div>
        <div><span>Obligaciones de deuda del ciclo</span><strong>- {money(formula.debt_commitment)}</strong></div>
        <div><span>Casa / Línea aún pendientes</span><strong>- {money(formula.mandatory_fixed_pending)}</strong></div>
        <div className="result"><span>Sobrante</span><strong>{money(formula.surplus)}</strong></div>
      </div>

      {Array.isArray(strategy.mandatory_fixed_pending_items) && strategy.mandatory_fixed_pending_items.length > 0 && (
        <div className="strategy-pending-obligations">
          {strategy.mandatory_fixed_pending_items.map((item) => (
            <span key={`${item.id}-${item.due_date}`}>{item.name} · {money(item.amount)} · vence {String(item.due_date || "").slice(5)}</span>
          ))}
        </div>
      )}

      <div className="strategy-allocation-v3">
        {allocationItems.length === 0 ? (
          <p className="muted-text">No hay sobrante para distribuir en este ciclo.</p>
        ) : allocationItems.map((item) => {
          const key = item.key;
          const percent = Number(item.percentage ?? allocation[key] ?? 0);
          const amount = Number(item.amount ?? allocationAmounts[key] ?? 0);
          return (
            <div className="strategy-allocation-row-v3" key={key}>
              <div><span>{allocationLabels[key] || key.replaceAll("_", " ")}</span><small>{percent.toFixed(1)}% del sobrante</small></div>
              <strong>{money(amount)}</strong>
            </div>
          );
        })}
      </div>

      <div className={`strategy-distribution-check ${distributionBalanced ? "ok" : "warning"}`}>
        {distributionBalanced ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
        <span>{distributionBalanced ? `Todo el sobrante está asignado: ${money(allocationTotal)}.` : `Revisar distribución: ${money(allocationTotal)} asignados de ${money(allocationBase)}.`}</span>
      </div>
    </div>
  );

  const detailRenderers = {
    salvavidas: renderSalvavidas,
    investments: renderInvestments,
    debts: renderDebtAdvice,
    distribution: renderDistribution,
  };

  return (
    <section className="page premium-strategy-page strategy-v3-page">
      <div className="page-section-header strategy-hero strategy-v3-hero">
        <div><span className="eyebrow">Director Financiero</span><h2>Strategy</h2><p>Una prioridad clara y cuatro herramientas. Nada más hasta que decidás qué querés revisar.</p></div>
        <button className="primary-action-button" onClick={runStrategy} disabled={state.running}>
          <RefreshCw size={18} className={state.running ? "spin" : ""} />
          {state.running ? "Recalculando..." : "Recalcular estrategia"}
        </button>
      </div>

      {state.error && <div className="alert-card"><AlertTriangle size={18} /> {state.error}</div>}

      <div className="strategy-priority-v3">
        <span className="strategy-v3-label">PRIORIDAD ACTUAL</span>
        <div className="strategy-title-row"><Shield size={22} /><div><h3>{priority.title || "Mantener control del flujo"}</h3><p>{priority.detail || strategy.mode_reason || strategy.objective}</p></div></div>
      </div>

      <div className="strategy-debt-progress-v3">
        <div className="progress-label-row"><span>Progreso de deudas</span><strong>{progress.toFixed(1)}%</strong></div>
        <div className="progress-track"><div style={{ width: `${progress}%` }} /></div>
        <div className="strategy-debt-progress-stats">
          <div><span>Falta</span><strong>{money(strategy.total_debt)}</strong></div>
          <div><span>Ya salió</span><strong>{money(strategy.debt_paid_total)}</strong></div>
          <div><span>Tiempo estimado</span><strong>{monthsText(strategy.estimated_total_months)}</strong></div>
          <div><span>Libre aprox.</span><strong>{strategy.estimated_debt_free_date ? formatDate(strategy.estimated_debt_free_date) : strategy.total_debt > 0 ? "Revisar cuota" : "Sin deuda"}</strong></div>
        </div>
      </div>

      <div className="strategy-options-v3">
        <span className="strategy-v3-label">¿QUÉ QUERÉS REVISAR?</span>
        {Object.entries(optionCopy).map(([key, option]) => {
          const Icon = option.icon;
          const active = activeSection === key;
          return (
            <button
              type="button"
              className={`strategy-option-card-v3 ${active ? "active" : ""}`}
              onClick={() => setActiveSection(active ? null : key)}
              aria-expanded={active}
              key={key}
            >
              <span className="strategy-option-icon-v3"><Icon size={21} /></span>
              <span><strong>{option.title}</strong><small>{option.subtitle}</small></span>
              <ChevronRight size={20} className={active ? "open" : ""} />
            </button>
          );
        })}
      </div>

      {activeSection && detailRenderers[activeSection]?.()}
    </section>
  );
}
