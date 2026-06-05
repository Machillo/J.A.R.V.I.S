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
  getFixedExpenseStatus,
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
      Number(item.loans) || 0,
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
        const loanHeight = Math.max((Number(item.loans) / maxValue) * 100, 0);
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
                className="flow-bar loans"
                style={{ height: `${loanHeight}%` }}
                title={`Préstamos ${formatCRC(item.loans)}`}
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

  useEffect(() => {
    let active = true;

    getTransactionAnalysis()
      .then((data) => {
        if (active) setTransactionAnalysis(data);
      })
      .catch((analysisError) => {
        console.error(analysisError);
        if (active) setTransactionAnalysis(null);
      });

    getFixedExpenseStatus()
      .then((data) => {
        if (active) setFixedStatus(data);
      })
      .catch((fixedError) => {
        console.error(fixedError);
        if (active) setFixedStatus(null);
      });

    return () => {
      active = false;
    };
  }, [dashboard]);

  if (loading) return <LoadingPanel />;
  if (error) return <ErrorPanel error={error} onRetry={onRefresh} />;

  const summary = dashboard?.summary || {};
  const alerts = dashboard?.alerts || [];
  const topDebts = dashboard?.top_debts || [];
  const recommendations = dashboard?.quick_recommendations || [];
  const goal = summary?.goals?.most_urgent_goal;

  const income = Number(summary?.income?.monthly_net_income) || 0;
  const totalIncome = Number(summary?.income?.total_income) || income;
  const expensesTotal = Number(summary?.expenses?.total_expenses) || 0;
  const fixedExpenses = Number(summary?.expenses?.fixed_expenses) || 0;
  const available = Number(summary?.cashflow?.available_cash) || 0;
  const debtTotal = Number(summary?.debts?.total) || 0;
  const monthlyDebtPayments = Number(summary?.debts?.monthly_payments) || 0;
  const netWorth = Number(summary?.assets?.net_worth) || 0;
  const assetsTotal = Number(summary?.assets?.assets_total) || 0;

  const goalProgress = goal?.target_amount
    ? clampPercent((Number(goal.current_amount) / Number(goal.target_amount)) * 100)
    : 0;

  const monthlyFlowData = useMemo(() => {
    return (transactionAnalysis?.monthly_flow || []).map((item) => ({
      ...item,
      income: Number(item.income) || 0,
      loans: Number(item.loans) || 0,
      expenses: Number(item.expenses) || 0,
      debt_payments: Number(item.debt_payments) || 0,
      outflow: Number(item.outflow) || 0,
      net_flow: Number(item.net_flow) || 0,
    }));
  }, [transactionAnalysis]);

  const latestFlow = monthlyFlowData[monthlyFlowData.length - 1] || null;
  const lastMonthIncome = latestFlow?.income ?? totalIncome;
  const lastMonthLoans = latestFlow?.loans ?? 0;
  const lastMonthExpenses = latestFlow?.expenses ?? expensesTotal;
  const lastMonthDebtPayments = latestFlow?.debt_payments ?? monthlyDebtPayments;
  const lastMonthAvailable = latestFlow
    ? latestFlow.net_flow
    : available;

  const debtProgress =
    lastMonthIncome > 0 ? clampPercent((lastMonthDebtPayments / lastMonthIncome) * 100) : 0;

  const categoryChartData = useMemo(() => {
    return (transactionAnalysis?.top_expense_categories || []).map((item) => ({
      category: item.category || "Sin categoría",
      total: Number(item.total) || 0,
    }));
  }, [transactionAnalysis]);

  const hasAnyTransactions = (transactionAnalysis?.summary?.total_transactions || 0) > 0;
  const isOwner = currentUser?.role === "owner" || currentUser?.email === "gatotico99@gmail.com";

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
      <div className="cards-grid">
        <article className="hud-card glow-green">
          <div className="card-header">
            <span>INGRESO NETO</span>
            <ArrowUpRight size={18} />
          </div>

          <MiniLine type="up" />

          <h2>{formatCRC(income)}</h2>
          <p>Sueldo neto proyectado</p>
        </article>

        <article className="hud-card glow-red">
          <div className="card-header">
            <span>DEUDA TOTAL</span>
            <ArrowDownRight size={18} />
          </div>

          <MiniLine type="down" />

          <h2>{formatCRC(debtTotal)}</h2>
          <p>Pasivos registrados</p>
        </article>

        <article className="hud-card">
          <div className="card-header">
            <span>META PRINCIPAL</span>
            <Target size={18} />
          </div>

          <div className="ring-row">
            <ProgressRing value={goalProgress} />
            <div>
              <h2>{goal?.name || "Sin meta"}</h2>
              <p>
                {goal
                  ? `${formatCRC(goal.current_amount)} de ${formatCRC(goal.target_amount)}`
                  : "Sin meta activa"}
              </p>
            </div>
          </div>
        </article>

        <article className="hud-card glow-red">
          <div className="card-header">
            <span>PAGOS DE DEUDA</span>
            <AlertTriangle size={18} />
          </div>

          <div className="ring-row">
            <ProgressRing value={debtProgress} color="red" />
            <div>
              <h2>{formatCRC(lastMonthDebtPayments)}</h2>
              <p>Pagos registrados en el último mes importado</p>
            </div>
          </div>
        </article>

        <article className="hud-card wide-balance">
          <div className="card-header">
            <span>SALDO REAL</span>
            <Wallet size={18} />
          </div>

          <h2 className={lastMonthAvailable < 0 ? "danger-text" : ""}>{formatCRC(lastMonthAvailable)}</h2>
          <p>Ingreso + préstamos - gastos - pagos del último mes</p>
        </article>
      </div>

      <div className="finance-kpi-strip">
        <article className="finance-mini-kpi">
          <span>Ingreso del último mes</span>
          <strong>{formatCRC(lastMonthIncome)}</strong>
        </article>
        <article className="finance-mini-kpi">
          <span>Préstamos recibidos</span>
          <strong>{formatCRC(lastMonthLoans)}</strong>
        </article>
        <article className="finance-mini-kpi">
          <span>Gastos del último mes</span>
          <strong>{formatCRC(lastMonthExpenses)}</strong>
        </article>
        <article className="finance-mini-kpi">
          <span>Histórico importado</span>
          <strong>{formatCRC(transactionAnalysis?.summary?.net_from_transactions || 0)}</strong>
        </article>
      </div>

      <div className="dashboard-grid finance-dashboard-grid">
        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>INGRESOS VS GASTOS</h3>
              <p>Datos reales registrados actualmente</p>
            </div>
            <span>REAL</span>
          </div>

          <MonthlyFlowChart data={monthlyFlowData} />

          <div className="legend">
            <span className="cyan"></span> Ingresos
            <span className="purple"></span> Préstamos
            <span className="red"></span> Gastos / deuda
          </div>
        </article>

        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>GASTOS POR CATEGORÍA</h3>
              <p>Lo que registremos por chat aparecerá aquí.</p>
            </div>
            <span>REAL</span>
          </div>

<CategoryBars data={categoryChartData} />
        </article>

        <FixedExpensesPanel data={fixedStatus} onRefresh={onRefresh} isOwner={isOwner} />

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>ALERTAS</h3>
              <p>Prioridad actual</p>
            </div>
          </div>

          <div className="alert-list">
            {alerts.length === 0 ? (
              <EmptyPanel
                title="Sin alertas críticas"
                description="Cuando haya riesgo de flujo, deuda o metas, aparecerá aquí."
              />
            ) : (
              alerts.map((alert, index) => (
                <div className={`alert-item ${alert.level}`} key={index}>
                  <AlertTriangle size={18} />
                  <span>{alert.message}</span>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>RESUMEN DE DEUDAS</h3>
              <p>Top deudas</p>
            </div>
          </div>

          <div className="debt-list">
            {topDebts.length === 0 ? (
              <EmptyPanel
                title="Sin deudas registradas"
                description="Las deudas que agregues desde Finanzas o chat aparecerán aquí."
              />
            ) : (
              topDebts.map((debt) => (
                <div className="debt-item" key={debt.id}>
                  <div className="debt-item-head">
                    <strong>{debt.name}</strong>
                    <span>{formatCRC(debt.remaining_amount)}</span>
                  </div>
                  <small>Pago: {formatCRC(debt.monthly_payment || 0)} · Interés: {Number(debt.interest_rate || 0)}%</small>

                  <div className="debt-bar">
                    <span
                      style={{
                        width: `${debtTotal > 0 ? Math.min((debt.remaining_amount / debtTotal) * 100, 100) : 0}%`,
                      }}
                    ></span>
                  </div>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>NET WORTH</h3>
              <p>Patrimonio neto</p>
            </div>
            <CircleDollarSign size={20} />
          </div>

          <h2 className={netWorth < 0 ? "danger-text" : "good-text"}>
            {formatCRC(netWorth)}
          </h2>

          <p className="muted">
            Activos registrados menos deudas registradas.
          </p>
        </article>

        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>RECOMENDACIONES</h3>
              <p>Acciones sugeridas por estado actual</p>
            </div>
          </div>

          {recommendations.length === 0 ? (
            <EmptyPanel
              title="Sin recomendaciones todavía"
              description="Cuando registremos ingresos, gastos, deudas y metas, Jarvis tendrá más contexto."
            />
          ) : (
            <div className="recommendation-list">
              {recommendations.map((item, index) => (
                <div className="recommendation-item" key={index}>
                  {item}
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="hud-panel">
          <div className="panel-title">
            <div>
              <h3>DATOS BASE</h3>
              <p>Estado del perfil financiero</p>
            </div>
          </div>

          <div className="metric-list">
            <div>
              <span>Gastos fijos</span>
              <strong>{formatCRC(fixedExpenses)}</strong>
            </div>
            <div>
              <span>Activos</span>
              <strong>{formatCRC(assetsTotal)}</strong>
            </div>
            <div>
              <span>Metas activas</span>
              <strong>{summary?.goals?.active_goals_count || 0}</strong>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
