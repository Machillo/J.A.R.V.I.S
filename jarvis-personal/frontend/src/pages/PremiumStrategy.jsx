import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Gift,
  LifeBuoy,
  RefreshCw,
  Save,
  Shield,
  TrendingUp,
} from "lucide-react";
import {
  getDebtAdvisory,
  getAguinaldo,
  getJarvisPremiumStrategyDashboard,
  getSalvavidas,
  updateSalvavidas,
} from "../services/jarvisApi";
import { trackEvent } from "../lib/telemetry";
import JarvisDisclosure from "../products/jarvis/components/JarvisDisclosure";
import { deviceLanguage, localeTag, t } from "../lib/locale";

const language = deviceLanguage();
const tr = (key) => t(key, language);
const tx = (es, en) => language === "es" ? es : en;
const monthUnit = (count) => count === 1 ? tx("mes", "month") : tx("meses", "months");

const money = (value) => `₡${Math.round(Number(value || 0)).toLocaleString(localeTag(language))}`;

const allocationLabels = {
  ataque_de_deuda: tx("Ataque extra a deuda", "Extra debt payment"),
  debt_attack: tx("Ataque extra a deuda", "Extra debt payment"),
  vida_controlada: tx("Libre para usar", "Free to spend"),
  controlled_life: tx("Libre para usar", "Free to spend"),
  fondo_de_emergencia: tr("strategy.lifebuoy"),
  emergency_buffer: tr("strategy.lifebuoy"),
  metas_o_inversion: tx("Metas / patrimonio", "Goals / wealth"),
  goals_or_investment: tx("Metas / patrimonio", "Goals / wealth"),
  meta_prioritaria: tx("Meta prioritaria", "Priority goal"),
  inversion: tx("Inversión", "Investment"),
};

const debtTypeLabels = {
  tasa_cero: tx("Tasa cero", "Zero-interest plan"),
  minicuotas: tx("Minicuotas", "Installments"),
  compra_financiada: tx("Compra financiada", "Financed purchase"),
  credit_card: tx("Tarjeta", "Card"),
  tarjeta: tx("Tarjeta", "Card"),
  personal_loan: tx("Préstamo", "Loan"),
  loan: tx("Préstamo", "Loan"),
  familiar: tx("Familiar", "Family"),
  other: tx("Deuda", "Debt"),
};

const formatDate = (value) => {
  if (!value) return tr("strategy.noDate");
  const parsed = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return tr("strategy.noDate");
  return new Intl.DateTimeFormat(localeTag(language), { month: "long", year: "numeric" }).format(parsed);
};

const monthsSaved = (count) => tx(`ahorra ${count} ${monthUnit(Number(count))}`, `saves ${count} ${monthUnit(Number(count))}`);
const newExpensesText = (count) => count === 1
  ? tx("1 gasto nuevo ya redujo este monto.", "1 new expense already reduced this amount.")
  : tx(`${count} gastos nuevos ya redujeron este monto.`, `${count} new expenses already reduced this amount.`);

const monthsText = (value) => {
  const months = Number(value || 0);
  if (!months) return "--";
  if (months >= 999) return tr("strategy.reviewPayment");
  return `${months} ${tr(months === 1 ? "common.month" : "common.months")}`;
};

const optionCopy = {
  salvavidas: {
    title: tr("strategy.lifebuoy"),
    subtitle: tx("Elegí y construí 1, 3 o 6 meses de cobertura.", "Choose and build 1, 3, or 6 months of coverage."),
    icon: LifeBuoy,
  },
  investments: {
    title: tr("strategy.investments"),
    subtitle: tx("Mirá cuánto podés invertir sin tocar obligaciones.", "See how much you can invest without touching obligations."),
    icon: TrendingUp,
  },
  debts: {
    title: tr("strategy.debtAdvice"),
    subtitle: tx("Analizá prioridad, impacto y ruta de salida.", "Review priority, impact, and payoff path."),
    icon: Activity,
  },
  distribution: {
    title: tr("strategy.distribution"),
    subtitle: tx("Repartí únicamente el sobrante real del ciclo.", "Allocate only the real surplus of the cycle."),
    icon: CircleDollarSign,
  },
  aguinaldo: {
    title: tr("strategy.bonus"),
    subtitle: tx("Calculá lo acumulado con tus salarios oficiales de la CCSS.", "Calculate what you’ve accrued from your official CCSS salaries."),
    icon: Gift,
  },
};

export default function PremiumStrategy({ api, brandName = "JARVIS" }) {
  const strategyApi = api || {
    getStrategyDashboard: getJarvisPremiumStrategyDashboard,
    getDebtAdvisory,
    getSalvavidas,
    updateSalvavidas,
    getAguinaldo,
  };
  const [state, setState] = useState({ loading: true, data: null, debtAdvice: null, error: "", running: false });
  const [activeSection, setActiveSection] = useState(null);
  const [salvavidasState, setSalvavidasState] = useState({ loading: true, saving: false, data: null, error: "" });
  const [salvavidasAmount, setSalvavidasAmount] = useState("");
  const [salvavidasTargetMonths, setSalvavidasTargetMonths] = useState(6);
  const [protectedExpenseIds, setProtectedExpenseIds] = useState([]);
  const [aguinaldoState, setAguinaldoState] = useState({ loading: true, data: null, error: "" });

  const load = async ({ keepPage = false } = {}) => {
    setState((current) => ({ ...current, loading: keepPage ? current.loading : true, running: keepPage, error: "" }));
    try {
      const strategyResult = await strategyApi.getStrategyDashboard();
      // Paint the useful strategy immediately. Debt simulations are secondary
      // and can be slow on a cold backend, so they hydrate progressively.
      setState((current) => ({ ...current, loading: false, data: strategyResult, error: "", running: false }));
      const strategyPayload = strategyResult?.strategy || {};
      strategyApi.getDebtAdvisory(Number(strategyPayload.debt_attack_extra || 0))
        .then((debtAdvice) => setState((current) => ({ ...current, debtAdvice })))
        .catch(() => {});
      return strategyResult;
    } catch (error) {
      setState((current) => ({
        loading: false,
        data: current.data,
        debtAdvice: current.debtAdvice,
        error: error.message || tr("strategy.loadError"),
        running: false,
      }));
      return null;
    }
  };

  const runStrategy = async () => {
    await Promise.all([load({ keepPage: true }), loadSalvavidas(), loadAguinaldo()]);
  };

  const loadAguinaldo = async () => {
    if (!strategyApi.getAguinaldo) return null;
    setAguinaldoState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const data = await strategyApi.getAguinaldo();
      setAguinaldoState({ loading: false, data, error: "" });
      return data;
    } catch (error) {
      setAguinaldoState({ loading: false, data: null, error: error.message || tx("No pude calcular el aguinaldo.", "I couldn’t calculate the year-end bonus.") });
      return null;
    }
  };

  const loadSalvavidas = async () => {
    setSalvavidasState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const data = await strategyApi.getSalvavidas();
      setSalvavidasState({ loading: false, saving: false, data, error: "" });
      setSalvavidasAmount(String(Number(data?.current_amount || 0)));
      setSalvavidasTargetMonths(Number(data?.target_months || 6));
      setProtectedExpenseIds(Array.isArray(data?.protected_expense_ids) ? data.protected_expense_ids : []);
      return data;
    } catch (error) {
      setSalvavidasState({ loading: false, saving: false, data: null, error: error.message || tx("No pude cargar el Salvavidas.", "I couldn’t load the emergency fund.") });
      return null;
    }
  };

  const saveSalvavidas = async () => {
    const amount = Number(salvavidasAmount || 0);
    if (!Number.isFinite(amount) || amount < 0) {
      setSalvavidasState((current) => ({ ...current, error: tx("El saldo del Salvavidas debe ser un monto válido mayor o igual a cero.", "The emergency fund balance must be a valid amount of zero or more.") }));
      return;
    }
    setSalvavidasState((current) => ({ ...current, saving: true, error: "" }));
    try {
      const data = await strategyApi.updateSalvavidas({
        current_amount: amount,
        protected_expense_ids: protectedExpenseIds,
        target_months: salvavidasTargetMonths,
      });
      setSalvavidasState({ loading: false, saving: false, data, error: "" });
      setSalvavidasAmount(String(Number(data?.current_amount || 0)));
      setSalvavidasTargetMonths(Number(data?.target_months || 6));
      setProtectedExpenseIds(Array.isArray(data?.protected_expense_ids) ? data.protected_expense_ids : []);
      trackEvent("salvavidas_saved", { target_months: Number(data?.target_months || salvavidasTargetMonths) });
      await load({ keepPage: true });
    } catch (error) {
      setSalvavidasState((current) => ({ ...current, saving: false, error: error.message || tx("No pude guardar el Salvavidas.", "I couldn’t save the emergency fund.") }));
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
    loadAguinaldo();
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
    return <section className="page premium-strategy-page"><div className="hud-card">{tr("strategy.loading")}</div></section>;
  }

  const investmentRecommended = Number(strategy.investment_recommended || 0);
  const investmentState = allocationBase <= 0 ? "blocked" : investmentRecommended > 0 ? "ready" : "limited";
  const formula = strategy.distribution_formula || {};
  const hasDistributionFormula = Object.prototype.hasOwnProperty.call(formula, "cash_available_now");
  const distributionDeficit = Math.max(0, Number(formula.deficit || 0));
  const distributionBreakdown = [
    [tx("Saldo disponible en MultiMoney", "Available MultiMoney balance"), formula.cash_available_now],
    [tx("Ingreso previsto aún por recibir", "Expected income not yet received"), formula.income],
    [tx("Gastos del estado de cuenta", "Statement expenses"), formula.statement_spending],
    [tx("Gastos nuevos después del corte", "New expenses after the cutoff"), formula.new_spending_after_cut],
    [tx("Cuotas de deuda pendientes", "Pending debt payments"), formula.debt_commitment],
    [tx("Gastos fijos pendientes", "Pending fixed expenses"), formula.mandatory_fixed_pending],
  ];
  const distributionBalanced = Math.abs(allocationBase - allocationTotal) <= 1;
  const distributionDestinations = [
    {
      key: "meta_prioritaria",
      label: strategy.goal_portfolio?.active_goal?.name
        ? `${tx("Meta activa", "Active goal")} · ${strategy.goal_portfolio.active_goal.name}`
        : tx("Meta activa", "Active goal"),
      amount: Number(allocationAmounts.meta_prioritaria || 0),
      optional: true,
    },
    {
      key: "fondo_de_emergencia",
      label: tr("strategy.lifebuoy"),
      amount: Number(allocationAmounts.fondo_de_emergencia || 0),
    },
    {
      key: "ataque_de_deuda",
      label: strategy.primary_debt_name
        ? `${tx("Deuda prioritaria", "Priority debt")} · ${strategy.primary_debt_name}`
        : tx("Deuda prioritaria", "Priority debt"),
      amount: Number(allocationAmounts.ataque_de_deuda || 0),
    },
    {
      key: "vida_controlada",
      label: tx("Uso libre", "Free to spend"),
      amount: Number(allocationAmounts.vida_controlada || 0),
    },
    {
      key: "inversion",
      label: tx("Inversión", "Investment"),
      amount: Number(allocationAmounts.inversion || 0),
    },
  ];

  const renderSalvavidas = () => (
    <div className="strategy-detail-panel salvavidas-panel strategy-v3-detail">
      <div className="strategy-detail-heading">
        <div className="strategy-title-row">
          <LifeBuoy size={22} />
          <div>
            <h3>{tr("strategy.lifebuoy")} · {salvavidasTargetMonths} {monthUnit(salvavidasTargetMonths)}</h3>
            <p>{tx("Deudas, Casa y Línea entran solas. Vos elegís qué otros gastos querés proteger.", "Debts, housing, and phone line are included automatically. You choose which other expenses to protect.")}</p>
          </div>
        </div>
        <span className="salvavidas-mode-badge">{tx("SALDO MANUAL", "MANUAL BALANCE")}</span>
      </div>

      {salvavidasState.error && <div className="alert-card"><AlertTriangle size={18} /> {salvavidasState.error}</div>}

      {salvavidasState.loading ? (
        <div className="salvavidas-loading">{tx("Calculando tu cobertura...", "Calculating your coverage...")}</div>
      ) : (
        <>
          <div className="salvavidas-summary-grid">
            <div><span>{tx("Objetivo", "Target")} {salvavidasTargetMonths} {monthUnit(salvavidasTargetMonths)}</span><strong>{money(salvavidas.target_amount)}</strong></div>
            <div><span>{tx("Guardado", "Saved")}</span><strong>{money(salvavidas.current_amount)}</strong></div>
            <div><span>{tx("Faltante", "Remaining")}</span><strong>{money(salvavidas.missing_amount)}</strong></div>
            <div><span>{tx("Cobertura", "Coverage")}</span><strong>{Number(salvavidas.coverage_months || 0).toFixed(1)} {tx("meses", "months")}</strong></div>
          </div>

          <div className="salvavidas-progress-block">
            <div className="progress-label-row"><span>{tx("Camino a", "Progress to")} {salvavidasTargetMonths} {monthUnit(salvavidasTargetMonths)}</span><strong>{salvavidasProgress.toFixed(0)}%</strong></div>
            <div className="progress-track"><div style={{ width: `${salvavidasProgress}%` }} /></div>
            <div className="salvavidas-milestones">
              {salvavidasMilestones.map((item) => (
                <button
                  type="button"
                  key={item.months}
                  className={`salvavidas-milestone ${item.reached ? "reached" : ""} ${salvavidasTargetMonths === item.months ? "selected" : ""}`}
                  onClick={() => {
                    setSalvavidasTargetMonths(item.months);
                    trackEvent("salvavidas_target_selected", { target_months: item.months });
                  }}
                  aria-pressed={salvavidasTargetMonths === item.months}
                >
                  {item.reached ? <CheckCircle2 size={16} /> : <span className="milestone-dot" />}
                  <span>{item.months} {monthUnit(item.months)}</span>
                  <strong>{money(item.target)}</strong>
                </button>
              ))}
            </div>
          </div>

          <div className="salvavidas-editor">
            <label className="salvavidas-amount-field">
              <span>{tx("¿Cuánto tenés guardado hoy?", "How much do you have saved today?")}</span>
              <div className="salvavidas-money-input">
                <span>₡</span>
                <input
                  type="number"
                  min="0"
                  step="1000"
                  inputMode="decimal"
                  value={salvavidasAmount}
                  onChange={(event) => setSalvavidasAmount(event.target.value)}
                  aria-label={tx("Saldo actual del Salvavidas", "Current emergency fund balance")}
                />
              </div>
            </label>

            <div className="strategy-v3-subsection">
              <div className="salvavidas-section-copy">
                <strong>{tx("Obligaciones automáticas", "Automatic obligations")}</strong>
                <small>{tx("No se pueden desmarcar y no vuelven a aparecer como gastos opcionales.", "They can’t be unchecked and won’t appear again as optional expenses.")}</small>
              </div>

              <div className="salvavidas-component-row locked">
                <div><span>{tx("Deudas activas", "Active debts")}</span><small>{tx("Incluye préstamos, Tasa Cero y Minicuotas mientras tengan saldo.", "Includes loans, zero-interest plans, and installments while they have a balance.")}</small></div>
                <strong>{money(salvavidas.components?.debt_monthly_payments)}</strong>
              </div>
              {salvavidasDebts.length > 0 && (
                <div className="salvavidas-debt-list">
                  {salvavidasDebts.map((debt) => (
                    <div key={debt.id}>
                      <span>{debt.name} <small>· {debtTypeLabels[debt.debt_type] || debt.debt_type || debtTypeLabels.other}</small></span>
                      <strong>{money(debt.monthly_payment)}{tx("/mes", "/mo")}</strong>
                    </div>
                  ))}
                </div>
              )}

              <div className="salvavidas-component-row locked">
                <div><span>{tx("Casa + Línea", "Housing + phone line")}</span><small>{tx(`Pagos recurrentes que ${brandName} protege siempre.`, `Recurring payments ${brandName} always protects.`)}</small></div>
                <strong>{money(salvavidas.components?.mandatory_fixed_expenses)}</strong>
              </div>
              {mandatoryExpenses.length > 0 && (
                <div className="salvavidas-debt-list">
                  {mandatoryExpenses.map((expense) => (
                    <div key={expense.id}><span>{expense.name}</span><strong>{money(expense.monthly_amount)}{tx("/mes", "/mo")}</strong></div>
                  ))}
                </div>
              )}
            </div>

            <div className="salvavidas-expense-section">
              <div className="salvavidas-section-copy">
                <strong>{tx("Otros gastos que querés proteger", "Other expenses you want to protect")}</strong>
                <small>{tx("Gym, Muay Thai, suscripciones u otros recurrentes: vos decidís.", "Gym, Muay Thai, subscriptions, or other recurring items: you decide.")}</small>
              </div>
              {salvavidasExpenses.length === 0 ? (
                <p className="muted-text">{tx("No hay otros gastos fijos activos para seleccionar.", "There are no other active fixed expenses to select.")}</p>
              ) : (
                <div className="salvavidas-expense-list">
                  {salvavidasExpenses.map((expense) => {
                    const checked = protectedExpenseIds.includes(expense.id);
                    return (
                      <label key={expense.id} className={`salvavidas-expense-option ${checked ? "selected" : ""}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleProtectedExpense(expense.id)} />
                        <span className="salvavidas-check">{checked ? <CheckCircle2 size={18} /> : null}</span>
                        <span className="salvavidas-expense-copy"><strong>{expense.name}</strong><small>{expense.category}</small></span>
                        <strong>{money(expense.monthly_amount)}{tx("/mes", "/mo")}</strong>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="salvavidas-base-total"><span>{tx("Costo mensual protegido", "Protected monthly cost")}</span><strong>{money(salvavidas.monthly_base)}</strong></div>

            <button className="primary-action-button salvavidas-save" type="button" onClick={saveSalvavidas} disabled={salvavidasState.saving}>
              <Save size={18} />
              {salvavidasState.saving ? tx("Guardando...", "Saving...") : tx("Guardar Salvavidas", "Save emergency fund")}
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
        <div className="strategy-title-row"><TrendingUp size={22} /><div><h3>{tr("strategy.investments")}</h3><p>{tx("Acá solo importa cuánto podés invertir sin tocar dinero comprometido.", "What matters here is how much you can invest without touching committed money.")}</p></div></div>
      </div>
      <div className={`strategy-investment-decision-card ${investmentState}`}>
        <span>{investmentState === "ready" ? tx("PODÉS INVERTIR", "YOU CAN INVEST") : investmentState === "blocked" ? tx("NO INVERTIR ESTE CICLO", "DON’T INVEST THIS CYCLE") : tx("MANTENER INVERSIÓN EN PAUSA", "KEEP INVESTING ON HOLD")}</span>
        <strong>{money(investmentRecommended)}</strong>
        <p>
          {investmentRecommended > 0
            ? tx(`Sale únicamente del sobrante real de ${money(allocationBase)} después de gastos y obligaciones.`, `It comes only from the real surplus of ${money(allocationBase)} after expenses and obligations.`)
            : allocationBase <= 0
              ? tx("No hay sobrante real después de cubrir lo registrado y lo obligatorio.", "There’s no real surplus after covering recorded and required expenses.")
              : tx("Hay sobrante, pero la estrategia actual lo necesita antes en otra prioridad.", "There’s a surplus, but the current strategy needs it first for another priority.")}
        </p>
      </div>
      <div className="strategy-v3-note">
        <Shield size={17} />
        <span>{tx("Saldo IBKR, rendimiento y posiciones siguen viviendo en Patrimonio/Inversiones; Estrategia no los duplica.", "IBKR balance, returns, and positions stay in Wealth/Investments; Strategy doesn’t duplicate them.")}</span>
      </div>
    </div>
  );

  const renderDebtAdvice = () => (
    <div className="strategy-detail-panel strategy-v3-detail">
      <div className="strategy-detail-heading">
        <div className="strategy-title-row"><Activity size={22} /><div><h3>{tr("strategy.debtAdvice")}</h3><p>{tx("Qué atacar, cuánto cambia el tiempo y qué ruta sigue cada deuda activa.", "What to tackle, how much the timeline changes, and the path for each active debt.")}</p></div></div>
      </div>

      <div className="strategy-debt-advice-summary">
        <span>{tx("Extra asignado a deuda este ciclo", "Extra assigned to debt this cycle")}</span>
        <strong>{money(strategy.debt_attack_extra)}</strong>
        <small>{debtAdvice.message || tx(`${brandName} recalcula la prioridad con tus datos activos.`, `${brandName} recalculates the priority with your active data.`)}</small>
      </div>

      {rankedAdvice.length === 0 ? (
        <p className="muted-text">{tx("No hay deudas activas para analizar.", "There are no active debts to analyze.")}</p>
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
                  <div><h4>{debt.name || debtTypeLabels.other}</h4><small>{debtTypeLabels[debt.debt_type] || (debt.debt_type ? String(debt.debt_type).replaceAll("_", " ") : debtTypeLabels.other)}</small></div>
                  <strong>{money(debt.remaining_amount)}</strong>
                </header>

                <div className="strategy-debt-mini-grid">
                  <div><span>{tx("Cuota", "Payment")}</span><strong>{money(debt.monthly_payment)}</strong></div>
                  <div><span>{tx("Tasa", "Rate")}</span><strong>{Number(debt.interest_rate || 0).toFixed(2)}%</strong></div>
                  <div><span>{tx("Solo mínimos", "Minimums only")}</span><strong>{monthsText(baseline.months)}</strong></div>
                </div>

                <p className="strategy-advice-line">{scenario.recommendation}</p>

                <div className="strategy-debt-options-v3">
                  <div className={recommended === "MINIMUM" ? "recommended" : ""}>
                    <span>{tx("Mantener mínimo", "Keep the minimum")}</span><strong>{money(debt.monthly_payment)}</strong><small>{monthsText(baseline.months)}</small>
                  </div>
                  <div className={recommended === "A" ? "recommended" : ""}>
                    <span>{tx("Abono mensual", "Monthly extra payment")}</span><strong>{money(amortization.payment)}</strong><small>{monthsText(amortization.months)}{amortization.months_saved_vs_minimum ? ` · ${monthsSaved(amortization.months_saved_vs_minimum)}` : ""}</small>
                  </div>
                  <div className={recommended === "B" ? "recommended" : ""}>
                    <span>{tx("Ahorrar y liquidar", "Save and pay off")}</span><strong>{money(save.monthly_saving)}</strong><small>{save.estimated_months_to_lump_sum ? tx(`${save.estimated_months_to_lump_sum} ${monthUnit(Number(save.estimated_months_to_lump_sum))} para acumular`, `${save.estimated_months_to_lump_sum} ${monthUnit(Number(save.estimated_months_to_lump_sum))} to save up`) : tx("Sin sobrante", "No surplus")}</small>
                  </div>
                  <div className={recommended === "C" ? "recommended" : ""}>
                    <span>{tx("Híbrida", "Hybrid")}</span><strong>{money(hybrid.payment)}</strong><small>{monthsText(hybrid.months)}{hybrid.months_saved_vs_minimum ? ` · ${monthsSaved(hybrid.months_saved_vs_minimum)}` : ""}</small>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <div className="strategy-route-v3">
        <div className="salvavidas-section-copy"><strong>{tx("Ruta de pago activa", "Active payoff path")}</strong><small>{tx("Las deudas pagadas o canceladas desaparecen; no quedan como “sin cierre”.", "Paid or canceled debts disappear; they don’t stay listed as “open”.")}</small></div>
        {timeline.length === 0 ? (
          <p className="muted-text">{tx("No hay deudas activas para proyectar.", "There are no active debts to project.")}</p>
        ) : (
          <div className="strategy-timeline">
            {timeline.map((item) => (
              <div className="timeline-item strategy-route-item" key={item.id || `${item.priority}-${item.name}`}>
                <span className="timeline-rank">#{item.priority}</span>
                <div><strong>{item.name}</strong><p>{tx("Saldo", "Balance")} {money(item.remaining_amount)} · {tx("objetivo", "target")} {money(item.recommended_payment)}{tx("/mes", "/mo")}</p></div>
                <b>{item.estimated_payoff_date ? formatDate(item.estimated_payoff_date) : tr("strategy.reviewPayment")}</b>
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
        <div className="strategy-title-row"><CircleDollarSign size={22} /><div><h3>{tr("strategy.distribution")}</h3><p>{tx(`${brandName} reparte solo lo que verdaderamente sobró después de pagos y gastos conocidos.`, `${brandName} allocates only what’s truly left after known payments and expenses.`)}</p></div></div>
      </div>

      <div className="strategy-surplus-card">
        <span>{tx("SOBRANTE REAL PARA REPARTIR", "REAL SURPLUS TO ALLOCATE")}</span>
        <strong>{money(allocationBase)}</strong>
        <small>{distributionDeficit > 0
          ? tx(`Los compromisos registrados superan los fondos previstos por ${money(distributionDeficit)}. Por eso no hay dinero para repartir en este ciclo.`, `Recorded commitments exceed expected funds by ${money(distributionDeficit)}, so there’s no money to allocate this cycle.`)
          : Number(strategy.new_expenses_after_cut_count || 0) > 0
            ? newExpensesText(Number(strategy.new_expenses_after_cut_count))
            : tx("Se recalcula cuando aparece un nuevo gasto.", "It’s recalculated when a new expense appears.")}</small>
      </div>

      {hasDistributionFormula && (
        <div className="strategy-allocation-v3" aria-label={tx("Cálculo de la distribución", "Allocation calculation")}>
          {distributionBreakdown.map(([label, amount], index) => (
            <div className="strategy-allocation-row-v3" key={label}>
              <div><span>{label}</span></div>
              <strong>{index < 2 ? "+" : "−"}{money(amount)}</strong>
            </div>
          ))}
          <div className="strategy-allocation-row-v3">
            <div><strong>{tx("Resultado antes de repartir", "Result before allocating")}</strong></div>
            <strong>{money(formula.surplus || 0)}{distributionDeficit > 0 ? ` · ${tx("faltan", "short by")} ${money(distributionDeficit)}` : ""}</strong>
          </div>
        </div>
      )}

      <div className="strategy-allocation-v3">
        {distributionDestinations.filter((item) => !item.optional || item.amount > 0).map((item) => (
          <div className="strategy-allocation-row-v3" key={item.key}>
            <div><span>{item.label}</span><small>{tx("Destino recomendado para este ciclo", "Recommended destination for this cycle")}</small></div>
            <strong>{money(item.amount)}</strong>
          </div>
        ))}
      </div>

      <div className={`strategy-distribution-check ${distributionBalanced ? "ok" : "warning"}`}>
        {distributionBalanced ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
        <span>{distributionBalanced ? tx(`Todo el sobrante está asignado: ${money(allocationTotal)}.`, `The whole surplus is allocated: ${money(allocationTotal)}.`) : tx(`Revisar distribución: ${money(allocationTotal)} asignados de ${money(allocationBase)}.`, `Review allocation: ${money(allocationTotal)} allocated out of ${money(allocationBase)}.`)}</span>
      </div>
    </div>
  );

  const renderAguinaldo = () => {
    const aguinaldo = aguinaldoState.data || {};
    const months = Array.isArray(aguinaldo.months) ? aguinaldo.months : [];
    return <div className="strategy-detail-panel strategy-v3-detail">
      <div className="strategy-detail-heading">
        <div className="strategy-title-row"><Gift size={22}/><div><h3>{tr("strategy.bonus")}</h3><p>{tx("Estimación basada en salarios reportados oficialmente, divididos entre 12.", "Estimate based on officially reported salaries, divided by 12.")}</p></div></div>
      </div>
      {aguinaldoState.loading ? <p className="muted-text">{tx("Calculando tu aguinaldo…", "Calculating your year-end bonus…")}</p> : aguinaldoState.error ? <div className="alert-card"><AlertTriangle size={18}/>{aguinaldoState.error}</div> : <>
        <div className="strategy-surplus-card"><span>{tx("AGUINALDO ACUMULADO", "ACCRUED YEAR-END BONUS")}</span><strong>{money(aguinaldo.accrued_aguinaldo)}</strong><small>{tx("Salarios contabilizados:", "Salaries counted:")} {money(aguinaldo.earned_salary_total)}</small></div>
        <div className="strategy-v3-note"><Shield size={17}/><span>{tx(`Período ${aguinaldo.period?.start || "—"} al ${aguinaldo.period?.end || "—"}. No incluye meses que todavía no tienen información salarial.`, `Period ${aguinaldo.period?.start || "—"} to ${aguinaldo.period?.end || "—"}. It doesn’t include months without salary information yet.`)}</span></div>
        {months.filter((item) => Number(item.total_earned || 0) > 0).length ? <div className="strategy-allocation-v3">{months.filter((item) => Number(item.total_earned || 0) > 0).map((item) => <div className="strategy-allocation-row-v3" key={item.month}><div><span>{item.month}</span><small>{Number(item.entries) === 1 ? tx("1 registro", "1 record") : tx(`${item.entries} registros`, `${item.entries} records`)}</small></div><strong>{money(item.total_earned)}</strong></div>)}</div> : <p className="muted-text">{tx("Todavía no hay salarios oficiales importados para este período.", "No official salaries have been imported for this period yet.")}</p>}
      </>}
    </div>;
  };

  const detailRenderers = {
    salvavidas: renderSalvavidas,
    investments: renderInvestments,
    debts: renderDebtAdvice,
    distribution: renderDistribution,
    aguinaldo: renderAguinaldo,
  };

  return (
    <section className="page premium-strategy-page strategy-v3-page strategy-v2">
      <header className={`strategy-v2-header ${brandName === "JARVIS" ? "strategy-v2-header--jarvis" : ""}`}>
        {brandName !== "JARVIS" && <div><span className="eyebrow">{tx("Director Financiero", "Financial Director")}</span><h2>{tr("nav.strategy")}</h2><p>{tx("Una prioridad clara y herramientas financieras probadas. Elegí qué querés revisar.", "A clear priority and proven financial tools. Choose what you want to review.")}</p></div>}
        <button className="primary-action-button" onClick={runStrategy} disabled={state.running}>
          <RefreshCw size={18} className={state.running ? "spin" : ""} />
          {state.running ? tx("Recalculando...", "Recalculating...") : tx("Recalcular estrategia", "Recalculate strategy")}
        </button>
      </header>

      {state.error && <div className="alert-card"><AlertTriangle size={18} /> {state.error}</div>}

      <JarvisDisclosure title={priority.title || tx("Mantener control del flujo", "Keep cash flow under control")} eyebrow={tx("Prioridad actual", "Current priority")} icon={Shield}>
        <div className="strategy-priority-v3 strategy-v2-priority"><p>{priority.detail || strategy.mode_reason || strategy.objective}</p></div>
      </JarvisDisclosure>

      <JarvisDisclosure title={tx("Progreso de deudas", "Debt progress")} summary={tx(`${progress.toFixed(1)}% completado`, `${progress.toFixed(1)}% complete`)} icon={Activity}>
      <section className="strategy-debt-progress-v3 strategy-v2-debt-summary">
        <div className="progress-label-row"><span>{tx("Progreso de deudas", "Debt progress")}</span><strong>{progress.toFixed(1)}%</strong></div>
        <div className="progress-track"><div style={{ width: `${progress}%` }} /></div>
        <div className="strategy-debt-progress-stats">
          <div><span>{tx("Falta", "Remaining")}</span><strong>{money(strategy.total_debt)}</strong></div>
          <div><span>{tx("Ya salió", "Paid off")}</span><strong>{money(strategy.debt_paid_total)}</strong></div>
          <div><span>{tx("Tiempo estimado", "Estimated time")}</span><strong>{monthsText(strategy.estimated_total_months)}</strong></div>
          <div><span>{tx("Libre aprox.", "Debt-free by")}</span><strong>{strategy.estimated_debt_free_date ? formatDate(strategy.estimated_debt_free_date) : strategy.total_debt > 0 ? tr("strategy.reviewPayment") : tx("Sin deuda", "No debt")}</strong></div>
        </div>
      </section>
      </JarvisDisclosure>

      <JarvisDisclosure title={tx("Herramientas financieras", "Financial tools")} summary={tx("Elegí qué querés revisar", "Choose what you want to review")} icon={CircleDollarSign}>
      <section className="strategy-options-v3 strategy-v2-tools">
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
      </section>
      </JarvisDisclosure>

      {activeSection && <section className="strategy-v2-active-detail">{detailRenderers[activeSection]?.()}</section>}
    </section>
  );
}
