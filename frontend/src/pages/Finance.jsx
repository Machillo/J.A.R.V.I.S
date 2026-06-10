import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CircleDollarSign,
  Target,
  Wallet,
  PlusCircle,
  Mic,
  FileText,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import {
  commitFinanceInput,
  getDebts,
  getFinanceCycleReport,
  getFixedExpenseStatus,
  getReceivables,
  getTransactionAnalysis,
  previewFinanceInput,
  previewFinancePdf,
  seedOwnerFixedExpenses,
} from "../services/jarvisApi";

const formatCRC = (value = 0) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const shortCRC = (value = 0) => {
  const number = Number(value) || 0;

  if (Math.abs(number) >= 1_000_000) {
    return `₡${(number / 1_000_000).toFixed(1)}M`;
  }

  if (Math.abs(number) >= 1_000) {
    return `₡${Math.round(number / 1_000)}k`;
  }

  return formatCRC(number);
};

const clampPercent = (value) =>
  Math.min(Math.max(Math.round(Number(value) || 0), 0), 100);

function MiniLine({ type = "up" }) {
  const points =
    type === "up"
      ? "0,35 18,28 33,32 50,20 70,24 90,10"
      : "0,18 18,12 33,20 50,17 70,28 90,35";

  return (
    <svg className={`mini-line ${type}`} viewBox="0 0 90 45">
      <polyline points={points} fill="none" strokeWidth="2" />
    </svg>
  );
}

function ProgressRing({ value = 0, color = "cyan" }) {
  const safeValue = clampPercent(value);

  return (
    <div className={`progress-ring ${color}`}>
      <div
        className="progress-ring-inner"
        style={{
          background: `conic-gradient(var(--ring-color) ${safeValue}%, rgba(255,255,255,.08) 0)`,
        }}
      >
        <div className="progress-ring-center">{safeValue}%</div>
      </div>
    </div>
  );
}

function LoadingPanel({ message = "Cargando núcleo financiero..." }) {
  return (
    <section className="dashboard-page">
      <div className="empty-state full-width">
        <div className="jarvis-loader"></div>
        <h3>{message}</h3>
        <p>Estoy sincronizando los datos reales de Supabase.</p>
      </div>
    </section>
  );
}

function ErrorPanel({ error, onRetry }) {
  return (
    <section className="dashboard-page">
      <div className="empty-state full-width danger">
        <AlertTriangle size={32} />
        <h3>No pude cargar el dashboard financiero</h3>
        <p>{error || "Revisa Render logs o vuelve a intentar."}</p>
        {onRetry && (
          <button className="hud-action-button" onClick={onRetry}>
            Reintentar
          </button>
        )}
      </div>
    </section>
  );
}

function EmptyPanel({ title, description }) {
  return (
    <div className="empty-state">
      <CircleDollarSign size={28} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

const formatMonthLabel = (month = "") => {
  const parts = String(month).split("-");
  if (parts.length !== 2) return month || "--";

  const [, monthNumber] = parts;
  return monthNumber;
};

function MonthlyFlowChart({ data = [] }) {
  const rows = data.slice(-6);
  const maxValue = Math.max(
    ...rows.flatMap((item) => [
      Number(item.income) || 0,
      Number(item.outflow) || 0,
    ]),
    1
  );

  if (rows.length === 0) {
    return (
      <EmptyPanel
        title="Sin movimientos"
        description="Cuando haya transacciones, el gráfico se activará."
      />
    );
  }

  return (
    <div className="jarvis-flow-chart">
      {rows.map((item) => {
        const incomeHeight = Math.max((Number(item.income) / maxValue) * 100, 2);
        const outflowHeight = Math.max((Number(item.outflow) / maxValue) * 100, 2);

        return (
          <div className="flow-month" key={item.month}>
            <div className="flow-bars">
              <span
                className="flow-bar income"
                style={{ height: `${incomeHeight}%` }}
                title={`Ingresos ${formatCRC(item.income)}`}
              />

              <span
                className="flow-bar outflow"
                style={{ height: `${outflowHeight}%` }}
                title={`Gastos/deuda ${formatCRC(item.outflow)}`}
              />
            </div>
            <strong>{formatMonthLabel(item.month)}</strong>
          </div>
        );
      })}
    </div>
  );
}


function FinanceInputPanel({ onSaved, compact = false }) {
  const [mode, setMode] = useState("text");
  const [text, setText] = useState("");
  const [month, setMonth] = useState("");
  const [exchangeRate, setExchangeRate] = useState(495);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const runPreview = async () => {
    if (!text.trim()) {
      setMessage("Pegá o escribí los movimientos primero.");
      return;
    }

    setLoading(true);
    setMessage("");
    try {
      const result = await previewFinanceInput({
        text,
        default_year_month: month || null,
        exchange_rate: Number(exchangeRate) || 495,
      });
      setPreview(result);
    } catch (error) {
      setMessage(error.message || "No pude analizar los movimientos.");
    } finally {
      setLoading(false);
    }
  };

  const runPdfPreview = async (file) => {
    if (!file) return;
    setLoading(true);
    setMessage("");
    try {
      const result = await previewFinancePdf({
        file,
        default_year_month: month || "",
        exchange_rate: Number(exchangeRate) || 495,
      });
      setPreview(result);
      setMode("preview");
    } catch (error) {
      setMessage(error.message || "No pude leer el PDF.");
    } finally {
      setLoading(false);
    }
  };

  const startVoice = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setMessage("Este navegador no soporta reconocimiento de voz.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "es-CR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      const spoken = event.results[0][0].transcript;
      setText((current) => `${current}${current ? "\n" : ""}${spoken}`);
      setMode("text");
    };

    recognition.onerror = () => setMessage("No pude escucharte bien.");
    recognition.start();
  };

  const savePreview = async () => {
    const transactions = preview?.transactions || [];
    if (!transactions.length) {
      setMessage("No hay movimientos listos para guardar.");
      return;
    }

    setLoading(true);
    setMessage("");
    try {
      await commitFinanceInput({ transactions });
      setMessage("Movimientos guardados.");
      setText("");
      setPreview(null);
      await onSaved?.();
    } catch (error) {
      setMessage(error.message || "No pude guardar los movimientos.");
    } finally {
      setLoading(false);
    }
  };

  const rows = preview?.transactions || [];
  const summary = preview?.summary || {};

  return (
    <article className={`hud-panel finance-input-panel ${compact ? "compact-empty" : ""}`}>
      <div className="panel-title finance-input-title">
        <div>
          <h3>AÑADIR FINANZAS</h3>
          <p>Escribí, hablá o subí un PDF. Jarvis categoriza y pregunta antes de guardar.</p>
        </div>
        <span>PREVIEW</span>
      </div>

      <div className="finance-input-actions">
        <button className={mode === "text" ? "active" : ""} onClick={() => setMode("text")}>
          <PlusCircle size={16} /> Escribir
        </button>
        <button onClick={startVoice}>
          <Mic size={16} /> Hablar
        </button>
        <label className="finance-file-button">
          <FileText size={16} /> PDF
          <input type="file" accept="application/pdf" onChange={(event) => runPdfPreview(event.target.files?.[0])} />
        </label>
      </div>

      <div className="finance-input-grid">
        <label>
          Mes base
          <input value={month} onChange={(event) => setMonth(event.target.value)} placeholder="2026-06" />
        </label>
        <label>
          Dólar
          <input type="number" value={exchangeRate} onChange={(event) => setExchangeRate(event.target.value)} />
        </label>
      </div>

      <textarea
        className="finance-input-textarea"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={'Ejemplo:\n2026-06-05 | Salario | 90000\n2026-06-06 | Uber Eats | 6500\n2026-06-07 | PlayStation | $11.99'}
      />

      <div className="finance-input-footer">
        <button className="hud-action-button" onClick={runPreview} disabled={loading}>
          Analizar
        </button>
        {rows.length > 0 && (
          <button className="hud-action-button success" onClick={savePreview} disabled={loading}>
            <CheckCircle2 size={16} /> Guardar {rows.length}
          </button>
        )}
      </div>

      {message && <p className="finance-input-message">{message}</p>}

      {preview && (
        <div className="finance-preview-box">
          <div className="finance-preview-summary">
            <span>Ingresos: <strong>{formatCRC(summary.income)}</strong></span>
            <span>Gastos: <strong>{formatCRC(summary.expenses)}</strong></span>
            <span>Deudas: <strong>{formatCRC(summary.debt_payment)}</strong></span>
            <span>Préstamos: <strong>{formatCRC(summary.loan_received)}</strong></span>
          </div>

          {preview.needs_review?.length > 0 && (
            <div className="finance-review-warning">
              <XCircle size={16} /> {preview.needs_review.length} línea(s) necesitan revisión.
            </div>
          )}

          <div className="finance-preview-table">
            {rows.slice(0, 12).map((item, index) => (
              <div className="finance-preview-row" key={`${item.transaction_date}-${index}`}>
                <span>{item.transaction_date}</span>
                <strong>{item.category}</strong>
                <em>{item.description}</em>
                <b>{formatCRC(item.amount)}</b>
              </div>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

function CategoryBars({ data = [] }) {
  const maxValue = Math.max(...data.map((item) => Number(item.total) || 0), 1);

  if (data.length === 0) {
    return (
      <EmptyPanel
        title="Sin categorías todavía"
        description="Cuando importemos enero a mayo, vas a ver en qué se va el dinero."
      />
    );
  }

  return (
    <div className="category-bars">
      {data.map((item) => {
        const width = Math.max((Number(item.total) / maxValue) * 100, 4);

        return (
          <div className="category-row" key={item.category}>
            <div className="category-row-head">
              <span>{item.category}</span>
              <strong>{formatCRC(item.total)}</strong>
            </div>
            <div className="category-track">
              <span style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}


function UnifiedFlowChart({ currentCycleFlow = [], yearly = [] }) {
  const [mode, setMode] = useState("month");
  const data = mode === "month" ? currentCycleFlow : yearly;
  return (
    <>
      <div className="chart-toggle">
        <button className={mode === "month" ? "active" : ""} onClick={() => setMode("month")}>Mes</button>
        <button className={mode === "year" ? "active" : ""} onClick={() => setMode("year")}>Año</button>
      </div>
      <MonthlyFlowChart data={data} />
    </>
  );
}


function ReceivablesPanel({ data }) {
  const items = data?.items || [];
  const summary = data?.summary || {};
  const openItems = items.filter((item) => item.status !== "completed" || Number(item.pending_amount) > 0);

  return (
    <article className="hud-panel large receivables-panel">
      <div className="panel-title">
        <div>
          <h3>CUENTAS POR COBRAR</h3>
          <p>Compras de tarjetas adicionales pendientes de pago.</p>
        </div>
        <span>{formatCRC(summary.total_pending || 0)}</span>
      </div>

      {openItems.length === 0 ? (
        <EmptyPanel
          title="Sin cuentas pendientes"
          description="Cuando Emily o Sidey tengan compras aceptadas, Jarvis las sumará automáticamente aquí."
        />
      ) : (
        <div className="receivable-list">
          {openItems.map((item) => {
            const original = Number(item.original_amount) || 0;
            const paid = Number(item.paid_amount) || 0;
            const pending = Number(item.pending_amount) || 0;
            const progress = original > 0 ? Math.min((paid / original) * 100, 100) : 0;
            return (
              <div className={`receivable-item ${item.status}`} key={item.id}>
                <div className="receivable-item-head">
                  <div>
                    <strong>{item.person_name}</strong>
                    <span>{item.is_auto ? "Tarjetas adicionales" : "Registro manual"}</span>
                  </div>
                  <b>{formatCRC(pending)}</b>
                </div>
                <div className="receivable-meta">
                  <span>Total: {formatCRC(original)}</span>
                  <span>Pagado: {formatCRC(paid)}</span>
                  <span>{item.status === "partial" ? "Pago parcial" : "Pendiente"}</span>
                </div>
                <div className="receivable-bar"><span style={{ width: `${progress}%` }} /></div>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

function FixedExpensesPanel({ data, onRefresh, isOwner }) {
  const items = data?.items || [];
  const summary = data?.summary || {};
  const alerts = data?.alerts || [];
  const [seeding, setSeeding] = useState(false);
  const statusLabels = {
    paid: "Pagado",
    pending: "Pendiente",
    overdue: "Vencido",
    doubtful: "Dudoso",
    not_due: "No toca",
  };

  const runSeed = async () => {
    setSeeding(true);
    try {
      await seedOwnerFixedExpenses();
      await onRefresh?.();
    } finally {
      setSeeding(false);
    }
  };

  return (
    <article className="hud-panel large fixed-expenses-panel">
      <div className="panel-title">
        <div>
          <h3>GASTOS FIJOS Y RECURRENTES</h3>
          <p>Jarvis detecta pagos parecidos y evita contarlos doble.</p>
        </div>
        <span>{data?.month || "MES"}</span>
      </div>

      <div className="fixed-summary-strip">
        <div><span>Esperado</span><strong>{formatCRC(summary.expected)}</strong></div>
        <div><span>Detectado</span><strong>{formatCRC(summary.paid)}</strong></div>
        <div><span>Pendiente</span><strong>{formatCRC(summary.pending + summary.overdue + summary.doubtful)}</strong></div>
      </div>

      {alerts.length > 0 && (
        <div className="fixed-alerts">
          {alerts.slice(0, 3).map((alert, index) => (
            <div className={`fixed-alert ${alert.level}`} key={index}>
              <AlertTriangle size={15} /> {alert.message}
            </div>
          ))}
        </div>
      )}

      {items.length === 0 ? (
        <div className="empty-state compact-empty-state">
          <CircleDollarSign size={24} />
          <h3>Sin gastos fijos</h3>
          <p>Podés agregarlos desde Jarvis o cargar los predeterminados.</p>
          {isOwner && (
            <button className="hud-action-button" onClick={runSeed} disabled={seeding}>
              Cargar mis gastos fijos
            </button>
          )}
        </div>
      ) : (
        <div className="fixed-expense-list">
          {items.map((item) => {
            const expense = item.fixed_expense || {};
            return (
              <div className={`fixed-expense-item ${item.status}`} key={expense.id}>
                <div>
                  <strong>{expense.name}</strong>
                  <span>{expense.category} · {item.due_date || "sin día fijo"}</span>
                </div>
                <div className="fixed-expense-right">
                  <b>{formatCRC(item.expected_amount)}</b>
                  <em>{statusLabels[item.status] || item.status}</em>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

export default function Finance({
  dashboard,
  loading = false,
  error = "",
  onRefresh,
  currentUser,
}) {
  const [transactionAnalysis, setTransactionAnalysis] = useState(null);
  const [fixedStatus, setFixedStatus] = useState(null);
  const [cycleReport, setCycleReport] = useState(null);
  const [debts, setDebts] = useState([]);
  const [receivables, setReceivables] = useState(null);
  const [debtSort, setDebtSort] = useState("saldo");
  const [detail, setDetail] = useState(null);

  const loadSupportingData = async () => {
    const [analysisResult, fixedResult, cycleResult, debtsResult, receivablesResult] = await Promise.allSettled([
      getTransactionAnalysis(),
      getFixedExpenseStatus(),
      getFinanceCycleReport(),
      getDebts(),
      getReceivables(),
    ]);

    setTransactionAnalysis(analysisResult.status === "fulfilled" ? analysisResult.value : null);
    setFixedStatus(fixedResult.status === "fulfilled" ? fixedResult.value : null);
    setCycleReport(cycleResult.status === "fulfilled" ? cycleResult.value : null);
    setDebts(debtsResult.status === "fulfilled" && Array.isArray(debtsResult.value) ? debtsResult.value : []);
    setReceivables(receivablesResult.status === "fulfilled" ? receivablesResult.value : null);
  };

  useEffect(() => {
    let active = true;
    loadSupportingData().catch((loadError) => {
      console.error(loadError);
      if (active) {
        setTransactionAnalysis(null);
        setFixedStatus(null);
        setCycleReport(null);
        setDebts([]);
        setReceivables(null);
      }
    });
    return () => {
      active = false;
    };
  }, [dashboard]);

  if (loading) return <LoadingPanel />;
  if (error) return <ErrorPanel error={error} onRetry={onRefresh} />;

  const summary = dashboard?.summary || {};
  const alerts = dashboard?.alerts || [];
  const recommendations = dashboard?.quick_recommendations || [];
  const fixedExpenses = Number(summary?.expenses?.fixed_expenses) || Number(fixedStatus?.summary?.expected) || 0;
  const debtTotal = Number(summary?.debts?.total) || 0;
  const assetsTotal = Number(summary?.assets?.assets_total) || 0;

  const cycleIncome = cycleReport?.income || {};
  const cycleExpenses = cycleReport?.expenses || {};
  const cycleDebts = cycleReport?.debts || {};
  const cycleCashflow = cycleReport?.cashflow || {};
  const cycleTransactions = cycleReport?.transactions || [];
  const fixedExpectedIncome = Number(cycleIncome.fixed_expected) || Number(summary?.income?.monthly_net_income) || 0;
  const extraExpectedIncome = Number(cycleIncome.extra_expected) || 0;
  const incomeNet = Number(cycleIncome.net) || Number(cycleIncome.expected_total) || fixedExpectedIncome + extraExpectedIncome;
  const currentExpenses = Number(cycleExpenses.current_period) || 0;
  const expenseNet = currentExpenses;
  const currentDebtPayments = Number(cycleDebts.payments_current_period) || 0;
  const realBalance = Number(cycleCashflow.real_balance) || Number(summary?.cashflow?.available_cash) || 0;
  const cycleLabel = cycleReport?.cycle?.label || "Ciclo 5 → 5";
  const expenseCycleLabel = cycleReport?.expense_cycle?.label || "Ciclo 21 → 21";

  const sortedDebts = useMemo(() => {
    const list = [...debts];
    const byNumber = (key) => (a, b) => (Number(b[key]) || 0) - (Number(a[key]) || 0);
    if (debtSort === "interes") return list.sort(byNumber("interest_rate"));
    if (debtSort === "cuota") return list.sort(byNumber("monthly_payment"));
    if (debtSort === "fecha") return list.sort((a, b) => (Number(a.payment_day) || 99) - (Number(b.payment_day) || 99));
    return list.sort(byNumber("remaining_amount"));
  }, [debts, debtSort]);

  const isOwner = currentUser?.role === "owner" || currentUser?.email === "gatotico99@gmail.com";
  const hasAnyTransactions = (transactionAnalysis?.summary?.total_transactions || 0) > 0;

  const expenseItems = cycleTransactions.filter((item) => item.transaction_type === "expense");

  const incomeItems = [
    {
      id: "fixed-income-current-cycle",
      transaction_date: cycleReport?.cycle?.start,
      description: "Salario fijo esperado",
      amount: fixedExpectedIncome,
      transaction_type: "salary_base",
      category: "Ingreso fijo",
    },
    ...(cycleIncome.items || []).map((item) => ({
      ...item,
      id: `income-${item.kind}-${item.id}`,
      transaction_date: item.estimated_pay_date,
      description: item.description || item.event_type || item.kind,
      amount: item.net_amount ?? item.amount,
      transaction_type: item.kind === "bonus" ? "bonus" : item.event_type,
      category: "Ingreso extra",
    })),
    ...cycleTransactions.filter((item) => item.transaction_type === "income"),
  ].filter((item) => Number(item.amount) !== 0);

  const balanceItems = [
    ...incomeItems.map((item) => ({ ...item, balance_side: "Ingreso" })),
    ...expenseItems.map((item) => ({ ...item, balance_side: "Salida" })),
  ];

  const debtItems = sortedDebts.map((debt) => ({
    id: `debt-${debt.id}`,
    description: debt.name || "Deuda",
    amount: Number(debt.remaining_amount) || 0,
    transaction_type: "debt",
    category: `Cuota ${formatCRC(debt.monthly_payment || 0)} · Interés ${Number(debt.interest_rate || 0)}%`,
    transaction_date: debt.payment_day ? `Día ${debt.payment_day}` : "sin fecha",
  }));

  const currentCycleFlow = [
    {
      month: "Actual",
      income: incomeNet,
      outflow: expenseNet,
    },
  ];

  const yearlyFlow = useMemo(() => {
    const monthly = transactionAnalysis?.monthly_flow || transactionAnalysis?.monthly_summary || [];
    if (Array.isArray(monthly) && monthly.length) {
      return monthly.map((item) => ({
        month: item.month || item.period || item.year_month || "--",
        income: Number(item.income || item.incomes || item.total_income) || 0,
        outflow: Number(item.outflow || item.expenses || item.total_expenses || item.expense) || 0,
      }));
    }
    return currentCycleFlow;
  }, [transactionAnalysis, incomeNet, expenseNet]);

  const categoryChartData = useMemo(() => {
    return (transactionAnalysis?.top_expense_categories || []).map((item) => ({
      category: item.category || "Sin categoría",
      total: Number(item.total) || 0,
    }));
  }, [transactionAnalysis]);

  const openDetail = (title, items = [], empty = "No hay movimientos para mostrar.") => {
    setDetail({ title, items, empty });
  };

  if (!isOwner && !hasAnyTransactions) {
    return (
      <section className="dashboard-page finance-empty-shell">
        <EmptyPanel
          title="Todavía no hay datos financieros"
          description="Añadí movimientos para activar los gráficos, categorías y recomendaciones."
        />
        <FinanceInputPanel onSaved={onRefresh} compact />
      </section>
    );
  }

  return (
    <section className="dashboard-page">
      <div className="finance-period-pill">Ingresos: {cycleLabel} · Gastos: {expenseCycleLabel}</div>

      <div className="cards-grid finance-main-cards finance-main-cards-clean">
        <button className="hud-card finance-click-card finance-simple-kpi glow-green" onClick={() => openDetail("Ingresos netos", incomeItems, "No hay ingresos registrados en este ciclo.")}> 
          <span>INGRESOS NETOS</span>
          <h2>{formatCRC(incomeNet)}</h2>
        </button>

        <button className="hud-card finance-click-card finance-simple-kpi glow-red" onClick={() => openDetail("Gastos netos", expenseItems, "No hay gastos registrados en este ciclo.")}> 
          <span>GASTOS NETOS</span>
          <h2>{formatCRC(expenseNet)}</h2>
        </button>

        <button className="hud-card finance-click-card finance-simple-kpi" onClick={() => openDetail("Saldo real", balanceItems, "No hay movimientos reales en este ciclo.")}> 
          <span>SALDO REAL</span>
          <h2 className={realBalance < 0 ? "danger-text" : ""}>{formatCRC(realBalance)}</h2>
        </button>

        <button className="hud-card finance-click-card finance-simple-kpi glow-purple" onClick={() => openDetail("Deuda total", debtItems, "No hay deudas registradas.")}> 
          <span>DEUDA TOTAL</span>
          <h2>{formatCRC(debtTotal)}</h2>
        </button>
      </div>

      {detail && (
        <div className="finance-detail-modal-backdrop" onClick={() => setDetail(null)}>
          <article className="hud-panel finance-detail-modal" onClick={(event) => event.stopPropagation()}>
            <div className="panel-title">
              <div>
                <h3>{detail.title}</h3>
                <p>Detalle del periodo actual.</p>
              </div>
              <button className="ghost-button" onClick={() => setDetail(null)}>Cerrar</button>
            </div>

            {detail.items?.length ? (
              <div className="finance-detail-list">
                {detail.items.map((item) => (
                  <div className="finance-detail-row" key={item.id || `${item.transaction_date}-${item.description}-${item.amount}`}>
                    <div><strong>{item.description}</strong><span>{item.transaction_date || item.estimated_pay_date || "sin fecha"} · {item.balance_side || item.category || item.transaction_type}</span></div>
                    <b>{formatCRC(item.amount ?? item.net_amount)}</b>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyPanel title="Sin detalle" description={detail.empty} />
            )}
          </article>
        </div>
      )}

      <div className="dashboard-grid finance-dashboard-grid">
        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>INGRESOS VS GASTOS</h3>
              <p>Ciclo actual 5 → 5 con ingresos esperados reales.</p>
            </div>
            <span>ACTUAL</span>
          </div>
          <UnifiedFlowChart currentCycleFlow={currentCycleFlow} yearly={yearlyFlow} />
          <div className="legend"><span className="cyan"></span> Ingresos neto <span className="red"></span> Gastos neto</div>
        </article>

        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>GASTOS POR CATEGORÍA</h3>
              <p>Compras aceptadas desde correos o agregadas manualmente.</p>
            </div>
            <span>REAL</span>
          </div>
          <CategoryBars data={categoryChartData} />
        </article>

        <ReceivablesPanel data={receivables} />

        <FixedExpensesPanel data={fixedStatus} onRefresh={onRefresh} isOwner={isOwner} />

        <article className="hud-panel large">
          <div className="panel-title debts-panel-title">
            <div>
              <h3>RESUMEN DE DEUDAS</h3>
              <p>Todas las deudas registradas.</p>
            </div>
            <select value={debtSort} onChange={(event) => setDebtSort(event.target.value)}>
              <option value="saldo">Saldo</option>
              <option value="interes">Interés</option>
              <option value="cuota">Cuota</option>
              <option value="fecha">Fecha de pago</option>
            </select>
          </div>

          <div className="debt-list full-debt-list">
            {sortedDebts.length === 0 ? (
              <EmptyPanel title="Sin deudas registradas" description="Las deudas que agregues desde Finanzas o chat aparecerán aquí." />
            ) : (
              sortedDebts.map((debt) => (
                <div className="debt-item" key={debt.id}>
                  <div className="debt-item-head"><strong>{debt.name}</strong><span>{formatCRC(debt.remaining_amount)}</span></div>
                  <small>Cuota: {formatCRC(debt.monthly_payment || 0)} · Interés: {Number(debt.interest_rate || 0)}% · Pago: {debt.payment_day || "--"}</small>
                  <div className="debt-bar"><span style={{ width: `${debtTotal > 0 ? Math.min((debt.remaining_amount / debtTotal) * 100, 100) : 0}%` }} /></div>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="hud-panel">
          <div className="panel-title"><div><h3>ALERTAS</h3><p>Prioridad actual</p></div></div>
          <div className="alert-list">
            {alerts.length === 0 ? <EmptyPanel title="Sin alertas críticas" description="Cuando haya riesgo de flujo, deuda o metas, aparecerá aquí." /> : alerts.map((alert, index) => <div className={`alert-item ${alert.level}`} key={index}><AlertTriangle size={18} /><span>{alert.message}</span></div>)}
          </div>
        </article>

        <article className="hud-panel large">
          <div className="panel-title"><div><h3>RECOMENDACIONES</h3><p>Acciones sugeridas por estado actual</p></div></div>
          {recommendations.length === 0 ? <EmptyPanel title="Sin recomendaciones todavía" description="Cuando registremos ingresos, gastos, deudas y metas, Jarvis tendrá más contexto." /> : <div className="recommendation-list">{recommendations.map((item, index) => <div className="recommendation-item" key={index}>{item}</div>)}</div>}
        </article>

        <article className="hud-panel">
          <div className="panel-title"><div><h3>DATOS BASE</h3><p>Estado del perfil financiero</p></div></div>
          <div className="metric-list">
            <div><span>Gastos fijos activos</span><strong>{formatCRC(fixedExpenses)}</strong></div>
            <div><span>Activos</span><strong>{formatCRC(assetsTotal)}</strong></div>
            <div><span>Metas activas</span><strong>{summary?.goals?.active_goals_count || 0}</strong></div>
          </div>
        </article>
      </div>
    </section>
  );
}
