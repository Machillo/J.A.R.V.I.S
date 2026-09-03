import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CircleDollarSign,
  PlusCircle,
  Mic,
  FileText,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import {
  commitFinanceInput,
  getDebts,
  createDebt,
  updateDebt,
  deleteDebt,
  registerDebtPayment,
  getFinanceCycleReport,
  getFixedExpenseStatus,
  addReceivableEntry,
  applyReceivablePayment,
  updateReceivableEntry,
  getTransactionAnalysis,
  previewFinanceInput,
  previewFinancePdf,
  seedOwnerFixedExpenses,
  getCurrencyAlerts,
  setCurrencyRate,
  getAguinaldo,
} from "../services/jarvisApi";

const formatCRC = (value = 0) =>
  new Intl.NumberFormat("es-CR", {
    style: "currency",
    currency: "CRC",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

// Real Balance must never hide its sign.  Formatting the absolute value and
// adding the sign ourselves makes a deficit unambiguous in every browser.
const formatSignedCRC = (value = 0) => {
  const number = Number(value) || 0;
  if (number < 0) return `-${formatCRC(Math.abs(number))}`;
  return formatCRC(number);
};

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
      {description ? <p>{description}</p> : null}
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

function SpendingDonut({ breakdown }) {
  const categories = Array.isArray(breakdown?.categories) ? breakdown.categories : [];
  const transactions = Array.isArray(breakdown?.transactions) ? breakdown.transactions : [];
  const total = Number(breakdown?.total) || categories.reduce((sum, item) => sum + (Number(item.total) || 0), 0);
  const [selectedCategory, setSelectedCategory] = useState(categories[0]?.category || "");

  useEffect(() => {
    if (!categories.length) {
      setSelectedCategory("");
      return;
    }
    if (!categories.some((item) => item.category === selectedCategory)) {
      setSelectedCategory(categories[0].category);
    }
  }, [categories, selectedCategory]);

  const selectedItems = useMemo(() =>
    transactions
      .filter((item) => item.category === selectedCategory)
      .sort((a, b) => String(b.transaction_date).localeCompare(String(a.transaction_date))),
    [transactions, selectedCategory]
  );

  const palette = ["#ff445f", "#8b5cf6", "#22d3ee", "#f59e0b", "#10b981", "#ec4899", "#60a5fa", "#a3e635", "#f97316", "#14b8a6", "#c084fc", "#fb7185"];

  if (!categories.length) {
    return <EmptyPanel title="Sin categorías todavía" description="Cuando haya gastos registrados, el gráfico se activará." />;
  }

  const tooltipContent = ({ active, payload }) => {
    if (!active || !payload?.length) return null;
    const row = payload[0]?.payload || {};
    const percent = total > 0 ? ((Number(row.total) || 0) / total) * 100 : 0;
    return (
      <div className="spending-donut-tooltip">
        <strong>{row.category}</strong>
        <span>{formatCRC(row.total)}</span>
        <small>{percent.toFixed(1)}% del gasto · {row.count || 0} movimientos</small>
      </div>
    );
  };

  return (
    <div className="spending-donut-workspace">
      <div className="spending-donut-main">
        <div className="spending-donut-chart">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={categories}
                dataKey="total"
                nameKey="category"
                cx="50%"
                cy="50%"
                innerRadius="57%"
                outerRadius="86%"
                paddingAngle={2}
                stroke="rgba(4, 14, 24, 0.9)"
                strokeWidth={3}
                onClick={(entry) => setSelectedCategory(entry?.category || "")}
              >
                {categories.map((item, index) => (
                  <Cell
                    key={item.category}
                    fill={palette[index % palette.length]}
                    opacity={!selectedCategory || selectedCategory === item.category ? 1 : 0.48}
                    className="spending-donut-slice"
                  />
                ))}
              </Pie>
              <Tooltip content={tooltipContent} />
            </PieChart>
          </ResponsiveContainer>
          <button className="spending-donut-center" onClick={() => setSelectedCategory("")} title="Mostrar total">
            <span>TOTAL YTD</span>
            <strong>{shortCRC(total)}</strong>
            <small>{breakdown?.period?.label || "Año actual"}</small>
          </button>
        </div>

        <div className="spending-donut-legend">
          {categories.map((item, index) => {
            const percent = total > 0 ? ((Number(item.total) || 0) / total) * 100 : 0;
            return (
              <button
                key={item.category}
                className={selectedCategory === item.category ? "active" : ""}
                onClick={() => setSelectedCategory(item.category)}
              >
                <i style={{ background: palette[index % palette.length] }} />
                <span><strong>{item.category}</strong><small>{item.count} movimientos · {percent.toFixed(1)}%</small></span>
                <b>{formatCRC(item.total)}</b>
              </button>
            );
          })}
        </div>
      </div>

      <div className="spending-category-detail">
        <div className="spending-category-detail-head">
          <div>
            <span>CATEGORÍA SELECCIONADA</span>
            <h4>{selectedCategory || "Todas"}</h4>
          </div>
          {selectedCategory ? <b>{formatCRC(categories.find((item) => item.category === selectedCategory)?.total || 0)}</b> : null}
        </div>
        {selectedCategory && selectedItems.length ? (
          <div className="finance-detail-list spending-drilldown-list">
            {selectedItems.map((item) => (
              <div className="finance-detail-row" key={item.id || `${item.transaction_date}-${item.description}-${item.amount}`}>
                <div>
                  <strong>{item.description}</strong>
                  <span>{item.transaction_date} · {item.synthetic ? "Gasto fijo recurrente" : item.source || "Transacción"}</span>
                </div>
                <b>{formatCRC(item.amount)}</b>
              </div>
            ))}
          </div>
        ) : (
          <EmptyPanel title="Seleccioná una categoría" description="Tocá una porción o una categoría para ver exactamente qué gastos contiene." />
        )}
      </div>
    </div>
  );
}


function MonthlyFinanceTrendChart({ monthly = [] }) {
  const rows = (Array.isArray(monthly) ? monthly : []).slice(-12);
  if (!rows.length) return <EmptyPanel title="No trend data yet" description="The chart will grow as monthly movements are recorded." />;

  const points = rows.map((item) => ({
    month: item.month,
    income: Number(item.income) || 0,
    expenses: Number(item.expenses) || 0,
    monthlyBalance: Number(item.monthly_balance ?? ((Number(item.income) || 0) - (Number(item.expenses) || 0))),
    cumulative: Number(item.cumulative_balance) || 0,
  }));

  const values = points.flatMap((item) => [item.income, item.expenses]);
  const max = Math.max(...values, 1);
  const width = 820;
  const height = 330;
  const padLeft = 82;
  const padRight = 28;
  const padTop = 28;
  const padBottom = 48;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  const x = (index) => padLeft + (index * plotWidth) / Math.max(points.length - 1, 1);
  const y = (value) => padTop + ((max - value) / max) * plotHeight;
  const incomePath = points.map((item, index) => `${index ? "L" : "M"}${x(index)},${y(item.income)}`).join(" ");
  const expensePath = points.map((item, index) => `${index ? "L" : "M"}${x(index)},${y(item.expenses)}`).join(" ");

  const highestIncome = points.reduce((best, item) => item.income > best.income ? item : best, points[0]);
  const highestExpenses = points.reduce((best, item) => item.expenses > best.expenses ? item : best, points[0]);
  const latest = points.at(-1);
  const accumulated = latest?.cumulative || 0;
  const accumulatedStatus = accumulated > 0 ? "SALDO A FAVOR" : accumulated < 0 ? "NEGATIVO" : "EN CERO";

  return (
    <div className="finance-trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Monthly income and expenses">
        {[0, 1, 2, 3, 4].map((line) => {
          const ratio = line / 4;
          const lineY = padTop + ratio * plotHeight;
          const labelValue = max * (1 - ratio);
          return (
            <g key={line}>
              <line x1={padLeft} x2={width - padRight} y1={lineY} y2={lineY} className="trend-grid-line" />
              <text x={padLeft - 12} y={lineY + 4} textAnchor="end" className="trend-axis-label">{shortCRC(labelValue)}</text>
            </g>
          );
        })}
        <path d={incomePath} className="trend-path capital" />
        <path d={expensePath} className="trend-path debt" />
        {points.map((item, index) => (
          <g key={item.month}>
            <circle cx={x(index)} cy={y(item.income)} r="6" className="trend-dot capital">
              <title>{`${formatMonthLabel(item.month)} · Income ${formatCRC(item.income)} · Expenses ${formatCRC(item.expenses)} · Balance ${formatCRC(item.monthlyBalance)}`}</title>
            </circle>
            <circle cx={x(index)} cy={y(item.expenses)} r="6" className="trend-dot debt">
              <title>{`${formatMonthLabel(item.month)} · Expenses ${formatCRC(item.expenses)} · Income ${formatCRC(item.income)} · Balance ${formatCRC(item.monthlyBalance)}`}</title>
            </circle>
            <text x={x(index)} y={height - 12} textAnchor="middle" className="trend-month-label">{formatMonthLabel(item.month)}</text>
          </g>
        ))}
      </svg>

      <div className="trend-summary-grid trend-summary-grid-four">
        <div className={accumulated < 0 ? "trend-negative" : accumulated > 0 ? "trend-positive" : ""}>
          <span>Accumulated balance</span>
          <strong>{formatCRC(accumulated)}</strong>
          <small>{accumulatedStatus} · sum of monthly leftovers</small>
        </div>
        <div>
          <span>Highest monthly income</span>
          <strong>{formatCRC(highestIncome.income)}</strong>
          <small>{formatMonthLabel(highestIncome.month)}</small>
        </div>
        <div>
          <span>Highest monthly expenses</span>
          <strong>{formatCRC(highestExpenses.expenses)}</strong>
          <small>{formatMonthLabel(highestExpenses.month)}</small>
        </div>
        <div className={latest?.monthlyBalance < 0 ? "trend-negative" : latest?.monthlyBalance > 0 ? "trend-positive" : ""}>
          <span>Latest month balance</span>
          <strong>{formatCRC(latest?.monthlyBalance || 0)}</strong>
          <small>{formatMonthLabel(latest?.month)} · income − expenses</small>
        </div>
      </div>
      <div className="legend trend-legend"><span className="cyan"></span> Income <span className="red"></span> Expenses</div>
      <small className="trend-history-note">Each point is that month's actual recorded total. Accumulated balance only carries forward the surplus or deficit left by each month; total debt is kept separately in Overview.</small>
    </div>
  );
}

export function ReceivablesPanel({ data, onPaymentSaved }) {
  const items = data?.items || [];
  const summary = data?.summary || {};
  const [activeId, setActiveId] = useState(null);
  const [historyId, setHistoryId] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [paymentMethod, setPaymentMethod] = useState("SINPE");
  const [paymentNotes, setPaymentNotes] = useState("");
  const [entryPerson, setEntryPerson] = useState("");
  const [entryAmount, setEntryAmount] = useState("");
  const [entryKind, setEntryKind] = useState("purchase");
  const [entryDescription, setEntryDescription] = useState("");
  const [entryDate, setEntryDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [editingEntry, setEditingEntry] = useState(null);

  const activeItem = items.find((item) => item.id === activeId) || null;

  const resetPayment = () => {
    setActiveId(null);
    setPaymentAmount("");
    setPaymentDate(new Date().toISOString().slice(0, 10));
    setPaymentMethod("SINPE");
    setPaymentNotes("");
    setMessage("");
  };

  const resetEntry = () => {
    setShowAdd(false);
    setEntryPerson("");
    setEntryAmount("");
    setEntryKind("purchase");
    setEntryDescription("");
    setEntryDate(new Date().toISOString().slice(0, 10));
    setMessage("");
  };

  const submitEntry = async (event) => {
    event.preventDefault();
    const amount = Number(String(entryAmount).replace(",", "."));
    if (!entryPerson.trim() || !amount || amount <= 0) {
      setMessage("Ingresá la persona y un monto válido.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      await addReceivableEntry({
        person_name: entryPerson.trim(),
        amount,
        description: entryDescription.trim(),
        entry_kind: entryKind,
        entry_date: entryDate,
      });
      resetEntry();
      await onPaymentSaved?.();
    } catch (error) {
      setMessage(error.message || "No pude guardar la cuenta por cobrar.");
    } finally {
      setSaving(false);
    }
  };

  const submitPayment = async (event) => {
    event.preventDefault();
    if (!activeItem) return;
    const amount = Number(String(paymentAmount).replace(",", "."));
    if (!amount || amount <= 0) {
      setMessage("Ingresá un monto válido.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      await applyReceivablePayment(activeItem.id, {
        amount,
        payment_date: paymentDate,
        method: paymentMethod,
        notes: paymentNotes,
      });
      resetPayment();
      await onPaymentSaved?.();
    } catch (error) {
      setMessage(error.message || "No pude registrar el pago.");
    } finally {
      setSaving(false);
    }
  };

  const saveEntryEdit = async (event) => {
    event.preventDefault();
    if (!editingEntry) return;
    const amount = Number(String(editingEntry.amount).replace(",", "."));
    if (!amount || amount <= 0) { setMessage("Ingresá un monto válido."); return; }
    setSaving(true); setMessage("");
    try {
      await updateReceivableEntry(editingEntry.receivable_id, editingEntry.id, { amount, description: editingEntry.description || "", entry_date: editingEntry.entry_date });
      setEditingEntry(null);
      await onPaymentSaved?.();
    } catch (error) { setMessage(error.message || "No pude editar el movimiento."); }
    finally { setSaving(false); }
  };

  const kindLabels = {
    purchase: "Compra",
    loan: "Préstamo",
    transfer: "Transferencia",
    cash: "Efectivo",
    other: "Otro",
  };

  return (
    <article className="hud-panel large receivables-panel">
      <div className="panel-title receivables-title-row">
        <h3>CUENTAS POR COBRAR</h3>
        <div className="receivables-title-actions">
          <span>{formatCRC(summary.total_pending || 0)}</span>
          <button type="button" className="hud-action-button small" onClick={() => { setShowAdd((value) => !value); resetPayment(); }}>
            <PlusCircle size={16} /> {showAdd ? "Cerrar" : "Agregar"}
          </button>
        </div>
      </div>

      {showAdd && (
        <form className="receivable-entry-form" onSubmit={submitEntry}>
          <label>Persona<input value={entryPerson} onChange={(e) => setEntryPerson(e.target.value)} placeholder="Emily, Mamá, Sidey..." /></label>
          <label>Monto<input type="number" min="1" step="0.01" inputMode="decimal" value={entryAmount} onChange={(e) => setEntryAmount(e.target.value)} /></label>
          <label>Tipo<select value={entryKind} onChange={(e) => setEntryKind(e.target.value)}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Fecha<input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} /></label>
          <label className="receivable-entry-description">Detalle<input value={entryDescription} onChange={(e) => setEntryDescription(e.target.value)} placeholder="Ej: gasolina, compra con mi tarjeta..." /></label>
          {message && <p className="form-message error">{message}</p>}
          <button className="hud-action-button" type="submit" disabled={saving}>{saving ? "Guardando..." : "Guardar"}</button>
        </form>
      )}

      {items.length === 0 ? (
        <EmptyPanel title="Sin cuentas registradas" description="" />
      ) : (
        <div className="receivable-list">
          {items.map((item) => {
            const carried = Number(item.carried_pending) || 0;
            const cycleCharges = Number(item.cycle_charges) || 0;
            const cyclePayments = Number(item.cycle_payments) || 0;
            const pending = Number(item.current_amount_due ?? item.pending_amount) || 0;
            const cycleBase = carried + cycleCharges;
            const progress = cycleBase > 0 ? Math.min((cyclePayments / cycleBase) * 100, 100) : 0;
            const isActive = activeId === item.id;
            const showHistory = historyId === item.id;
            return (
              <div className={`receivable-item ${item.status} ${isActive ? "active" : ""}`} key={item.id}>
                <div className="receivable-item-head"><strong>{item.person_name}</strong><b>{formatCRC(pending)}</b></div>
                <div className="receivable-meta current-cycle">
                  {carried !== 0 && <span>Saldo anterior: {formatCRC(carried)}</span>}
                  <span>Cargos del ciclo: {formatCRC(cycleCharges)}</span>
                  {cyclePayments > 0 && <span>Pagos del ciclo: {formatCRC(cyclePayments)}</span>}
                  <span className="receivable-current-total">Debe ahora: {formatCRC(pending)}</span>
                </div>
                <div className="receivable-bar"><span style={{ width: `${progress}%` }} /></div>
                <div className="receivable-actions">
                  <button type="button" className="ghost-button" onClick={() => setHistoryId(showHistory ? null : item.id)}>{showHistory ? "Ocultar historial" : "Historial"}</button>
                  <button type="button" className="ghost-button receivable-payment-toggle" onClick={() => { if (isActive) resetPayment(); else { setActiveId(item.id); setPaymentAmount(""); setPaymentDate(new Date().toISOString().slice(0, 10)); setMessage(""); setShowAdd(false); } }}>{isActive ? "Cancelar" : "Registrar pago"}</button>
                </div>

                {showHistory && (
                  <div className="receivable-history">
                    {(item.history || []).length === 0 ? <span>Sin movimientos.</span> : (item.history || []).map((entry) => (
                      <div className={`receivable-history-row ${entry.entry_type}`} key={entry.id}>
                        <div><strong>{entry.description || (entry.entry_type === "payment" ? "Pago" : "Cargo")}</strong><span>{String(entry.entry_date || "").slice(0, 10)}</span></div>
                        <div className="receivable-history-actions"><b>{entry.entry_type === "payment" ? "−" : "+"}{formatCRC(entry.amount)}</b>{entry.source_type !== "additional_card_auto" && <button type="button" className="ghost-button small" onClick={() => setEditingEntry({ ...entry, receivable_id: item.id, entry_date: String(entry.entry_date || "").slice(0,10) })}>Editar</button>}</div>
                      </div>
                    ))}
                  </div>
                )}

                {editingEntry?.receivable_id === item.id && (
                  <form className="receivable-payment-form receivable-edit-form" onSubmit={saveEntryEdit}>
                    <label>Monto<input type="number" min="0.01" step="0.01" value={editingEntry.amount} onChange={(e) => setEditingEntry({ ...editingEntry, amount: e.target.value })} /></label>
                    <label>Fecha<input type="date" value={editingEntry.entry_date} onChange={(e) => setEditingEntry({ ...editingEntry, entry_date: e.target.value })} /></label>
                    <label className="receivable-payment-notes">Detalle<input value={editingEntry.description || ""} onChange={(e) => setEditingEntry({ ...editingEntry, description: e.target.value })} /></label>
                    <button className="hud-action-button" type="submit" disabled={saving}>{saving ? "Guardando..." : "Guardar cambios"}</button>
                    <button className="ghost-button" type="button" onClick={() => setEditingEntry(null)}>Cancelar</button>
                  </form>
                )}

                {isActive && (
                  <form className="receivable-payment-form" onSubmit={submitPayment}>
                    <label>Monto recibido<input type="number" min="1" step="0.01" inputMode="decimal" value={paymentAmount} onChange={(e) => setPaymentAmount(e.target.value)} /></label>
                    <label>Fecha<input type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} /></label>
                    <label>Método<select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}><option>SINPE</option><option>Transferencia</option><option>Efectivo</option><option>Otro</option></select></label>
                    <label className="receivable-payment-notes">Nota<input value={paymentNotes} onChange={(e) => setPaymentNotes(e.target.value)} placeholder="Opcional" /></label>
                    {message && <p className="form-message error">{message}</p>}
                    <button className="hud-action-button" type="submit" disabled={saving}>{saving ? "Guardando..." : "Guardar pago"}</button>
                  </form>
                )}
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


const emptyDebtForm = {
  name: "",
  debt_type: "tasa_cero",
  total_amount: "",
  remaining_amount: "",
  monthly_payment: "",
  interest_rate: "0",
  term_months: "3",
  payment_day: "5",
  start_date: new Date().toISOString().slice(0, 10),
  first_payment_date: "",
  installments_paid: "0",
  auto_update_monthly: true,
  interest_method: "monthly",
  fixed_fee_amount: "0",
};

function DebtFormModal({ debt, onClose, onSaved }) {
  const [form, setForm] = useState(() => {
    if (!debt) return emptyDebtForm;
    return {
      name: debt.name || "",
      debt_type: debt.debt_type || "other",
      total_amount: debt.total_amount ?? "",
      remaining_amount: debt.remaining_amount ?? "",
      monthly_payment: debt.monthly_payment_raw ?? debt.monthly_payment ?? "",
      interest_rate: debt.interest_rate ?? 0,
      term_months: debt.term_months ?? debt.total_installments ?? "",
      payment_day: debt.payment_day ?? "5",
      start_date: debt.start_date ?? debt.registered_date ?? "",
      first_payment_date: debt.first_payment_date ?? "",
      installments_paid: debt.paid_installments ?? debt.installments_paid ?? 0,
      auto_update_monthly: debt.auto_update_monthly !== false,
      interest_method: debt.interest_method || "monthly",
      fixed_fee_amount: debt.fixed_fee_amount ?? 0,
    };
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const setValue = (key, value) => {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if ((key === "total_amount" || key === "remaining_amount" || key === "term_months") && !debt) {
        const remaining = Number(String(next.remaining_amount || next.total_amount).replace(",", ".")) || 0;
        const months = Number(next.term_months) || 0;
        if (remaining > 0 && months > 0 && ["tasa_cero", "minicuotas", "compra_financiada"].includes(next.debt_type)) {
          next.monthly_payment = String(Math.round((remaining / months) * 100) / 100);
        }
      }
      if (key === "debt_type" && value === "tasa_cero") next.interest_rate = "0";
      return next;
    });
  };

  const buildPayload = () => {
    const total = Number(String(form.total_amount).replace(",", ".")) || 0;
    const remaining = Number(String(form.remaining_amount || form.total_amount).replace(",", ".")) || total;
    const months = form.term_months === "" ? null : Number(form.term_months) || null;
    let monthly = Number(String(form.monthly_payment).replace(",", ".")) || 0;
    if (!monthly && remaining > 0 && months) monthly = Math.round((remaining / months) * 100) / 100;
    return {
      name: form.name.trim(),
      debt_type: form.debt_type,
      total_amount: total,
      remaining_amount: remaining,
      monthly_payment: monthly,
      interest_rate: Number(String(form.interest_rate).replace(",", ".")) || 0,
      term_months: months,
      payment_day: form.payment_day === "" ? null : Number(form.payment_day) || null,
      start_date: form.start_date || null,
      first_payment_date: form.first_payment_date || null,
      installments_paid: Math.max(Number(form.installments_paid) || 0, 0),
      auto_update_monthly: Boolean(form.auto_update_monthly),
      interest_method: form.interest_method || "monthly",
      fixed_fee_amount: Number(String(form.fixed_fee_amount).replace(",", ".")) || 0,
    };
  };

  const submit = async (event) => {
    event.preventDefault();
    const payload = buildPayload();
    if (!payload.name || payload.total_amount <= 0 || payload.remaining_amount <= 0 || !payload.start_date || !payload.first_payment_date) {
      setMessage("Nombre, montos, fecha de inicio y primera cuota son obligatorios.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      if (debt?.id) await updateDebt(debt.id, payload);
      else await createDebt(payload);
      await onSaved?.();
      onClose();
    } catch (error) {
      setMessage(error.message || "No pude guardar la deuda.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="finance-detail-modal-backdrop" onClick={onClose}>
      <article className="hud-panel finance-detail-modal debt-editor-modal" onClick={(event) => event.stopPropagation()}>
        <div className="panel-title">
          <div><h3>{debt ? "EDITAR DEUDA" : "AGREGAR DEUDA"}</h3></div>
          <button className="ghost-button" onClick={onClose}>Cerrar</button>
        </div>

        <form className="debt-form-grid" onSubmit={submit}>
          <label>
            Nombre
            <input value={form.name} onChange={(event) => setValue("name", event.target.value)} placeholder="Mochila Chimborazo" />
          </label>
          <label>
            Tipo
            <select value={form.debt_type} onChange={(event) => setValue("debt_type", event.target.value)}>
              <option value="tasa_cero">Tasa cero</option>
              <option value="minicuotas">Minicuotas</option>
              <option value="compra_financiada">Compra financiada</option>
              <option value="tarjeta">Tarjeta</option>
              <option value="prestamo">Préstamo</option>
              <option value="other">Otro</option>
            </select>
          </label>
          <label>
            Monto total
            <input type="number" value={form.total_amount} onChange={(event) => setValue("total_amount", event.target.value)} placeholder="107400" />
          </label>
          <label>
            Saldo pendiente
            <input type="number" value={form.remaining_amount} onChange={(event) => setValue("remaining_amount", event.target.value)} placeholder="107400" />
          </label>
          <label>
            Meses
            <input type="number" value={form.term_months} onChange={(event) => setValue("term_months", event.target.value)} placeholder="3" />
          </label>
          <label>
            Cuota mensual
            <input type="number" value={form.monthly_payment} onChange={(event) => setValue("monthly_payment", event.target.value)} placeholder="35800" />
          </label>
          <label>
            Interés %
            <input type="number" step="0.01" value={form.interest_rate} onChange={(event) => setValue("interest_rate", event.target.value)} />
          </label>
          <label>
            Cálculo de interés
            <select value={form.interest_method} onChange={(event) => setValue("interest_method", event.target.value)}>
              <option value="monthly">Mensual sobre saldo</option>
              <option value="daily_365">Diario / 365 sobre saldo</option>
            </select>
          </label>
          <label>
            Seguro / cargo fijo mensual
            <input type="number" step="0.01" value={form.fixed_fee_amount} onChange={(event) => setValue("fixed_fee_amount", event.target.value)} placeholder="0" />
          </label>
          <label>
            Día de pago
            <input type="number" min="1" max="31" value={form.payment_day} onChange={(event) => setValue("payment_day", event.target.value)} placeholder="5" />
          </label>
          <label>
            Fecha de compra o inicio
            <input type="date" value={form.start_date} onChange={(event) => setValue("start_date", event.target.value)} />
          </label>
          <label>
            Primera cuota
            <input type="date" value={form.first_payment_date} onChange={(event) => setValue("first_payment_date", event.target.value)} />
          </label>
          <label>
            Cuotas ya pagadas
            <input type="number" min="0" max={form.term_months || undefined} value={form.installments_paid} onChange={(event) => setValue("installments_paid", event.target.value)} />
          </label>
          <label className="debt-auto-update-toggle">
            <span>Actualización automática</span>
            <input type="checkbox" checked={Boolean(form.auto_update_monthly)} onChange={(event) => setValue("auto_update_monthly", event.target.checked)} />
          </label>

          <div className="debt-form-preview">
            <strong>Cuota estimada</strong>
            <span>{formatCRC(buildPayload().monthly_payment)}</span>
          </div>

          {message && <p className="finance-input-message">{message}</p>}

          <button className="hud-action-button success debt-form-submit" disabled={saving}>
            {saving ? "Guardando..." : debt ? "Guardar cambios" : "Agregar deuda"}
          </button>
        </form>
      </article>
    </div>
  );
}

function DebtPaymentModal({ debt, onClose, onSaved }) {
  const [amount, setAmount] = useState(String(debt?.monthly_payment || ""));
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    const value = Number(String(amount).replace(",", ".")) || 0;
    if (value <= 0) {
      setMessage("Ingresá un pago mayor que cero.");
      return;
    }
    setSaving(true);
    setMessage("");
    setResult(null);
    try {
      const response = await registerDebtPayment(debt.id, {
        amount: value,
        payment_date: paymentDate || null,
        description,
      });
      if (response?.status === "ERROR") throw new Error(response.message || "No pude registrar el pago.");
      setResult(response);
      await onSaved?.();
    } catch (error) {
      setMessage(error.message || "No pude registrar el pago.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="finance-detail-modal-backdrop" onClick={onClose}>
      <article className="hud-panel finance-detail-modal debt-editor-modal" onClick={(event) => event.stopPropagation()}>
        <div className="panel-title">
          <div><h3>REGISTRAR PAGO · {debt.name}</h3></div>
          <button className="ghost-button" onClick={onClose}>Cerrar</button>
        </div>
        <form className="debt-form-grid" onSubmit={submit}>
          <label>
            Pago realizado
            <input type="number" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </label>
          <label>
            Fecha del pago
            <input type="date" value={paymentDate} onChange={(event) => setPaymentDate(event.target.value)} />
          </label>
          <label>
            Nota
            <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Opcional" />
          </label>

          <div className="debt-form-preview">
            <strong>Cuota normal</strong>
            <span>{formatCRC(debt.monthly_payment || 0)}</span>
          </div>
          <div className="debt-form-preview">
            <strong>Saldo antes del pago</strong>
            <span>{formatCRC(debt.remaining_amount || 0)}</span>
          </div>

          {result && (
            <div className="finance-input-message success">
              <strong>Pago aplicado</strong><br />
              Interés: {formatCRC(result.interest_amount)} · Cargos: {formatCRC(result.fee_amount)}<br />
              Principal: {formatCRC(result.principal_amount)}
              {Number(result.extra_principal_amount || 0) > 0 ? <> · Extra a principal: {formatCRC(result.extra_principal_amount)}</> : null}<br />
              Nuevo saldo: <strong>{formatCRC(result.new_remaining_amount)}</strong>
            </div>
          )}
          {message && <p className="finance-input-message">{message}</p>}
          <button className="hud-action-button success debt-form-submit" disabled={saving}>
            {saving ? "Calculando..." : "Registrar pago"}
          </button>
        </form>
      </article>
    </div>
  );
}

function DebtsPanel({ sortedDebts, debtSort, setDebtSort, onChanged }) {
  const [editingDebt, setEditingDebt] = useState(null);
  const [adding, setAdding] = useState(false);
  const [payingDebt, setPayingDebt] = useState(null);
  const [message, setMessage] = useState("");

  const removeDebt = async (debt) => {
    if (!window.confirm(`¿Eliminar ${debt.name}?`)) return;
    setMessage("");
    try {
      await deleteDebt(debt.id);
      await onChanged?.();
    } catch (error) {
      setMessage(error.message || "No pude eliminar la deuda.");
    }
  };

  return (
    <article className="hud-panel large">
      <div className="panel-title debts-panel-title">
        <div><h3>RESUMEN DE DEUDAS</h3></div>
        <div className="debt-panel-actions">
          <button className="hud-action-button small" onClick={() => setAdding(true)}>+ Agregar</button>
          <select value={debtSort} onChange={(event) => setDebtSort(event.target.value)}>
            <option value="saldo">Saldo</option>
            <option value="interes">Interés</option>
            <option value="cuota">Cuota</option>
            <option value="fecha">Fecha de pago</option>
          </select>
        </div>
      </div>

      {message && <p className="finance-input-message">{message}</p>}

      <div className="debt-list full-debt-list">
        {sortedDebts.length === 0 ? (
          <EmptyPanel title="Sin deudas registradas" description="" />
        ) : (
          sortedDebts.map((debt) => {
            const paid = Number(debt.installments_paid ?? debt.paid_installments ?? 0);
            const total = Number(debt.term_months ?? debt.total_installments ?? 0);
            const remaining = total > 0 ? Math.max(total - paid, 0) : null;
            const progress = total > 0 ? Math.min((paid / total) * 100, 100) : 0;
            const isPaid = Number(debt.remaining_amount || 0) <= 0 || (total > 0 && paid >= total);
            const scheduleLabel = total > 0 ? `${paid}/${total}` : "Pago libre";
            return (
              <div className={`debt-item debt-card-v2 ${isPaid ? "is-paid" : ""}`} key={debt.id}>
                <div className="debt-card-top">
                  <div>
                    <strong className="debt-card-name">{debt.name}</strong>
                    <span className="debt-card-type">{String(debt.debt_type || "other").replaceAll("_", " ")}</span>
                  </div>
                  <div className="debt-card-balance">
                    <small>Saldo</small>
                    <b>{formatCRC(debt.remaining_amount)}</b>
                  </div>
                </div>

                <div className="debt-progress-copy">
                  <strong>{scheduleLabel}{total > 0 ? " cuotas" : ""}</strong>
                  <span>{isPaid ? "Pagada" : remaining == null ? "Sin calendario automático" : remaining === 1 ? "Resta 1 cuota" : `Restan ${remaining} cuotas`}</span>
                </div>
                <div className="debt-bar debt-progress-bar" aria-label={`${Math.round(progress)}% pagado`}>
                  <span style={{ width: `${progress}%` }} />
                </div>

                <div className="debt-metrics-grid">
                  <span><small>Cuota mensual</small><b>{formatCRC(debt.monthly_payment || 0)}</b></span>
                  <span><small>Interés</small><b>{Number(debt.interest_rate || 0)}%</b></span>
                  <span><small>Cargo fijo</small><b>{formatCRC(debt.fixed_fee_amount || 0)}</b></span>
                  <span><small>Método</small><b>{debt.interest_method === "daily_365" ? "Diario / 365" : "Mensual"}</b></span>
                  <span><small>Próximo pago</small><b>{isPaid ? "Finalizada" : debt.next_payment_date || "Sin fecha"}</b></span>
                  <span><small>Último pago</small><b>{debt.last_payment_date || "Sin registrar"}</b></span>
                </div>

                <details className="debt-schedule-details">
                  <summary>Ver calendario</summary>
                  <div className="debt-date-grid">
                    <span><b>Registrada</b>{debt.registered_date || debt.start_date || "--"}</span>
                    <span><b>Inicio</b>{debt.start_date || "--"}</span>
                    <span><b>Primera cuota</b>{debt.first_payment_date || "--"}</span>
                    <span><b>Hoy</b>{debt.current_date || "--"}</span>
                  </div>
                </details>

                <div className="debt-row-actions">
                  {!isPaid && <button className="ghost-button" onClick={() => setPayingDebt(debt)}>Registrar pago</button>}
                  <button className="ghost-button" onClick={() => setEditingDebt(debt)}>Editar</button>
                  <button className="ghost-button danger" onClick={() => removeDebt(debt)}>Eliminar</button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {payingDebt && (
        <DebtPaymentModal
          debt={payingDebt}
          onClose={() => setPayingDebt(null)}
          onSaved={onChanged}
        />
      )}

      {(adding || editingDebt) && (
        <DebtFormModal
          debt={editingDebt}
          onClose={() => { setAdding(false); setEditingDebt(null); }}
          onSaved={onChanged}
        />
      )}
    </article>
  );
}

function CurrencyAlertsPanel({ alerts, onApplied }) {
  const dates = alerts?.dates || [];
  const [rateByDate, setRateByDate] = useState({});
  const [savingDate, setSavingDate] = useState(null);
  const [message, setMessage] = useState("");

  const applyRate = async (date) => {
    const rate = Number(rateByDate[date]);
    if (!rate || rate <= 0) {
      setMessage("Ingresá un tipo de cambio válido.");
      return;
    }
    setSavingDate(date);
    setMessage("");
    try {
      await setCurrencyRate(date, rate);
      setRateByDate((current) => ({ ...current, [date]: "" }));
      await onApplied?.();
    } catch (error) {
      setMessage(error.message || "No pude guardar el tipo de cambio.");
    } finally {
      setSavingDate(null);
    }
  };

  return (
    <article className="hud-panel large currency-alert-panel">
      <div className="panel-title">
        <div><h3>USD CONVERSION</h3></div>
        <span>{alerts?.total || 0} PENDING</span>
      </div>
      {dates.length === 0 ? (
        <EmptyPanel title="All USD transactions converted" description="No hay compras en dólares pendientes de tipo de cambio." />
      ) : (
        <div className="currency-alert-list">
          {dates.map((group) => (
            <div className="currency-alert-row" key={group.date}>
              <div>
                <strong>{group.date}</strong>
                <span>{group.count} movimiento{group.count === 1 ? "" : "s"} · ${Number(group.total_usd || 0).toFixed(2)} USD</span>
              </div>
              <div className="currency-rate-editor">
                <label>USD → CRC<input type="number" min="0.01" step="0.01" placeholder="Ej. 505.25" value={rateByDate[group.date] || ""} onChange={(e) => setRateByDate((current) => ({ ...current, [group.date]: e.target.value }))} /></label>
                <button className="hud-action-button small" onClick={() => applyRate(group.date)} disabled={savingDate === group.date}>
                  {savingDate === group.date ? "Guardando..." : "Aplicar"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {message && <p className="finance-input-message">{message}</p>}
      <small className="currency-alert-note">Una tasa se aplica a todas las transacciones USD pendientes de esa misma fecha y queda guardada en cada movimiento.</small>
    </article>
  );
}

function IncomePanel({ cycleIncome, cycleTransactions, fixedExpectedIncome, extraExpectedIncome }) {
  const actualItems = (cycleTransactions || []).filter((item) => item.transaction_type === "income");
  const actual = actualItems.reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const expected = (Number(fixedExpectedIncome) || 0) + (Number(extraExpectedIncome) || 0);
  const variance = actual - expected;
  const items = [
    { id: "expected-salary", description: "Expected fixed salary", amount: fixedExpectedIncome, category: "Expected", transaction_date: cycleIncome?.cycle?.start },
    ...(cycleIncome?.items || []).map((item) => ({ id: `expected-${item.kind}-${item.id}`, description: item.description || item.event_type || item.kind, amount: item.net_amount ?? item.amount, category: "Expected extra", transaction_date: item.estimated_pay_date })),
    ...actualItems.map((item) => ({ ...item, category: item.category || "Income" })),
  ].filter((item) => Number(item.amount) !== 0);

  return (
    <div className="finance-income-workspace">
      <div className="cards-grid finance-main-cards finance-income-cards">
        <article className="hud-card finance-simple-kpi glow-green"><span>EXPECTED INCOME</span><h2>{formatCRC(expected)}</h2></article>
        <article className="hud-card finance-simple-kpi glow-green"><span>ACTUAL INCOME</span><h2>{formatCRC(actual)}</h2></article>
        <article className="hud-card finance-simple-kpi"><span>VARIANCE</span><h2 className={variance < 0 ? "danger-text" : ""}>{formatCRC(variance)}</h2></article>
      </div>
      <article className="hud-panel large">
        <div className="panel-title"><div><h3>INCOME HISTORY</h3></div><span>CURRENT CYCLE</span></div>
        {items.length ? <div className="finance-detail-list">{items.map((item) => <div className="finance-detail-row" key={item.id || `${item.transaction_date}-${item.description}`}><div><strong>{item.description}</strong><span>{item.transaction_date || "No date"} · {item.category}</span></div><b>{formatCRC(item.amount)}</b></div>)}</div> : <EmptyPanel title="No income recorded" description="Registered income will appear here." />}
      </article>
    </div>
  );
}

function AguinaldoPanel({ data }) {
  if (!data) return <LoadingPanel message="Calculando tu aguinaldo real..." />;
  const period = data.period || {};
  const sources = data.source_totals || {};
  const months = data.months || [];
  return (
    <div className="finance-income-workspace aguinaldo-workspace">
      <div className="cards-grid finance-main-cards finance-income-cards">
        <article className="hud-card finance-simple-kpi glow-green"><span>AGUINALDO ACUMULADO</span><h2>{formatCRC(data.accrued_aguinaldo)}</h2></article>
        <article className="hud-card finance-simple-kpi"><span>SALARIO COMPUTABLE</span><h2>{formatCRC(data.earned_salary_total)}</h2></article>
        <article className="hud-card finance-simple-kpi"><span>PERÍODO</span><h2 className="aguinaldo-period-value">{period.start?.slice(0, 7)} → {period.end?.slice(0, 7)}</h2></article>
      </div>
      <article className="hud-panel large">
        <div className="panel-title"><div><h3>CÁLCULO DEL AGUINALDO</h3><p>Actualizado al {period.calculated_through || "--"}</p></div><span>÷ 12</span></div>
        <div className="aguinaldo-source-grid">
          <div><span>Órdenes patronales CCSS</span><strong>{formatCRC(sources.ccss_salary)}</strong></div>
          <div><span>Respaldo salarial manual</span><strong>{formatSignedCRC((Number(sources.salary) || 0) + (Number(sources.payroll_event) || 0) + (Number(sources.bonus) || 0))}</strong></div>
        </div>
        <small className="aguinaldo-note">La Orden Patronal es la fuente principal. El respaldo manual solo se utiliza en meses donde todavía no existe una orden de la CCSS.</small>
      </article>
      <article className="hud-panel large">
        <div className="panel-title"><div><h3>DESGLOSE MENSUAL</h3></div><span>{months.length} MESES</span></div>
        <div className="finance-detail-list">{months.map((item) => <div className="finance-detail-row" key={item.month}><div><strong>{item.month}</strong><span>{item.entries ? `${item.entries} registro${item.entries === 1 ? "" : "s"}` : "Sin salario registrado"}</span></div><b>{formatSignedCRC(item.total_earned)}</b></div>)}</div>
      </article>
    </div>
  );
}

export default function Finance({
  dashboard,
  loading = false,
  error = "",
  onRefresh,
  currentUser,
}) {
  const [activeTab, setActiveTab] = useState("overview");
  const [transactionAnalysis, setTransactionAnalysis] = useState(null);
  const [fixedStatus, setFixedStatus] = useState(null);
  const [cycleReport, setCycleReport] = useState(null);
  const [cycleReportError, setCycleReportError] = useState("");
  const [debts, setDebts] = useState([]);
  const [debtSort, setDebtSort] = useState("saldo");
  const [detail, setDetail] = useState(null);
  const [currencyAlerts, setCurrencyAlerts] = useState(null);
  const [aguinaldo, setAguinaldo] = useState(null);
  const [financeAsOf, setFinanceAsOf] = useState(() => new Date().toISOString().slice(0, 10));

  const loadSupportingData = async () => {
    const [analysisResult, fixedResult, cycleResult, debtsResult, currencyResult, aguinaldoResult] = await Promise.allSettled([
      getTransactionAnalysis(), getFixedExpenseStatus(), getFinanceCycleReport(financeAsOf), getDebts(), getCurrencyAlerts(), getAguinaldo(),
    ]);
    setTransactionAnalysis(analysisResult.status === "fulfilled" ? analysisResult.value : null);
    setFixedStatus(fixedResult.status === "fulfilled" ? fixedResult.value : null);
    if (cycleResult.status === "fulfilled") {
      setCycleReport(cycleResult.value);
      setCycleReportError("");
    } else {
      setCycleReport(null);
      setCycleReportError(cycleResult.reason?.message || "Finance cycle could not be loaded.");
    }
    setDebts(debtsResult.status === "fulfilled" && Array.isArray(debtsResult.value) ? debtsResult.value : []);
    setCurrencyAlerts(currencyResult.status === "fulfilled" ? currencyResult.value : null);
    setAguinaldo(aguinaldoResult.status === "fulfilled" ? aguinaldoResult.value : null);
  };

  useEffect(() => { loadSupportingData().catch(console.error); }, [dashboard, financeAsOf]);
  if (loading) return <LoadingPanel />;
  if (error) return <ErrorPanel error={error} onRetry={onRefresh} />;

  const summary = dashboard?.summary || {};
  const alerts = dashboard?.alerts || [];
  const debtTotal = Number(summary?.debts?.total) || debts.reduce((sum, debt) => sum + (Number(debt.remaining_amount) || 0), 0);
  const cycleIncome = cycleReport?.income || {};
  const cycleExpenses = cycleReport?.expenses || {};
  const cycleCashflow = cycleReport?.cashflow || {};
  const cycleTransactions = cycleReport?.transactions || [];
  const fixedExpectedIncome = Number(cycleIncome.fixed_expected) || Number(summary?.income?.monthly_net_income) || 0;
  const extraExpectedIncome = Number(cycleIncome.extra_expected) || 0;
  const incomeNet = Number(cycleIncome.net) || Number(cycleIncome.expected_total) || fixedExpectedIncome + extraExpectedIncome;
  const expenseNet = cycleReport ? (Number(cycleExpenses.current_period) || 0) : null;
  const realBalance = Number(cycleCashflow.real_balance) || Number(summary?.cashflow?.available_cash) || 0;
  const cycleLabel = cycleReport?.cycle?.label || "Cycle 5 → 5";
  const expenseCycleLabel = cycleReport?.expense_cycle?.label || "Cycle 21 → 21";

  const sortedDebts = (() => {
    const list = [...debts];
    const byNumber = (key) => (a, b) => (Number(b[key]) || 0) - (Number(a[key]) || 0);
    if (debtSort === "interes") return list.sort(byNumber("interest_rate"));
    if (debtSort === "cuota") return list.sort(byNumber("monthly_payment"));
    if (debtSort === "fecha") return list.sort((a, b) => (Number(a.payment_day) || 99) - (Number(b.payment_day) || 99));
    return list.sort(byNumber("remaining_amount"));
  })();

  const expenseItems = cycleTransactions.filter((item) => ["expense", "debt_payment"].includes(item.transaction_type));
  const recentExpenses = [...expenseItems].sort((a, b) => String(b.transaction_date).localeCompare(String(a.transaction_date))).slice(0, 12);
  const incomeItems = [
    { id: "fixed-income-current-cycle", transaction_date: cycleReport?.cycle?.start, description: "Expected fixed salary", amount: fixedExpectedIncome, transaction_type: "salary_base", category: "Fixed income" },
    ...(cycleIncome.items || []).map((item) => ({ ...item, id: `income-${item.kind}-${item.id}`, transaction_date: item.estimated_pay_date, description: item.description || item.event_type || item.kind, amount: item.net_amount ?? item.amount, category: "Extra income" })),
    ...cycleTransactions.filter((item) => item.transaction_type === "income"),
  ].filter((item) => Number(item.amount) !== 0);
  const balanceItems = [...incomeItems.map((item) => ({ ...item, balance_side: "Income" })), ...expenseItems.map((item) => ({ ...item, balance_side: "Outflow" }))];
  const debtItems = sortedDebts.map((debt) => ({ id: `debt-${debt.id}`, description: debt.name || "Debt", amount: Number(debt.remaining_amount) || 0, category: `Payment ${formatCRC(debt.monthly_payment || 0)} · Interest ${Number(debt.interest_rate || 0)}%`, transaction_date: debt.payment_day ? `Day ${debt.payment_day}` : "No fixed date" }));
  const monthlyFlow = transactionAnalysis?.monthly_flow || [];
  const spendingBreakdown = transactionAnalysis?.spending_breakdown || {
    categories: (transactionAnalysis?.top_expense_categories || []).map((item) => ({ category: item.category || "Uncategorized", total: Number(item.total) || 0, count: Number(item.count) || 0 })),
    transactions: [],
    total: 0,
  };
  const isOwner = currentUser?.role === "owner";
  const openDetail = (title, items = [], empty = "No movements to display.") => setDetail({ title, items, empty });

  return (
    <section className="dashboard-page finance-workspace">
      <div className="finance-tab-bar" role="tablist" aria-label="Finance sections">
        <button className={activeTab === "overview" ? "active" : ""} onClick={() => setActiveTab("overview")}>Overview</button>
        <button className={activeTab === "analytics" ? "active" : ""} onClick={() => setActiveTab("analytics")}>Analytics</button>
        <button className={activeTab === "spending" ? "active" : ""} onClick={() => setActiveTab("spending")}>Spending</button>
        <button className={activeTab === "income" ? "active" : ""} onClick={() => setActiveTab("income")}>Income</button>
        <button className={activeTab === "aguinaldo" ? "active" : ""} onClick={() => setActiveTab("aguinaldo")}>Aguinaldo</button>
      </div>

      {activeTab === "overview" && <>
        <div className="finance-period-controls">
          <div className="finance-period-pill">Financial cycle: {cycleLabel} · Expense cutoff: {expenseCycleLabel}{cycleReport?.expense_cycle?.closed ? " · Closed" : " · Open"}</div>
          <label className="finance-asof-picker">View as of <input type="date" value={financeAsOf} onChange={(e) => setFinanceAsOf(e.target.value)} /></label>
        </div>
        <div className="cards-grid finance-main-cards finance-main-cards-clean">
          <button className="hud-card finance-click-card finance-simple-kpi glow-green" onClick={() => openDetail("Net income", incomeItems)}><span>NET INCOME</span><h2>{formatCRC(incomeNet)}</h2></button>
          <button className="hud-card finance-click-card finance-simple-kpi glow-red" onClick={() => openDetail("Net expenses", expenseItems)}><span>NET EXPENSES</span><h2>{expenseNet === null ? "—" : formatCRC(expenseNet)}</h2>{cycleReportError ? <small className="danger-text">Cycle report unavailable</small> : null}</button>
          <button className="hud-card finance-click-card finance-simple-kpi" onClick={() => openDetail("Real balance", balanceItems)}><span>REAL BALANCE</span><h2 className={realBalance < 0 ? "danger-text" : realBalance > 0 ? "good-text" : ""}>{formatSignedCRC(realBalance)}</h2></button>
          <button className="hud-card finance-click-card finance-simple-kpi glow-purple" onClick={() => openDetail("Total debt", debtItems)}><span>TOTAL DEBT</span><h2>{formatCRC(debtTotal)}</h2></button>
        </div>
        <div className="dashboard-grid finance-dashboard-grid finance-overview-grid">
          <DebtsPanel sortedDebts={sortedDebts} debtSort={debtSort} setDebtSort={setDebtSort} onChanged={async () => { await loadSupportingData(); await onRefresh?.(); }} />
          <article className="hud-panel"><div className="panel-title"><div><h3>ALERTS</h3></div></div><div className="alert-list">{alerts.length === 0 ? <EmptyPanel title="No critical alerts" description="JARVIS will flag cash-flow and debt risks here." /> : alerts.map((alert, index) => <div className={`alert-item ${alert.level}`} key={index}><AlertTriangle size={18} /><span>{alert.message}</span></div>)}</div></article>
        </div>
      </>}

      {activeTab === "analytics" && <div className="dashboard-grid finance-dashboard-grid finance-analytics-grid">
        <article className="hud-panel large finance-trend-panel"><div className="panel-title"><div><h3>MONTHLY FINANCIAL TREND</h3></div><span>INCOME VS EXPENSES</span></div><MonthlyFinanceTrendChart monthly={monthlyFlow} /></article>
      </div>}

      {activeTab === "spending" && <div className="dashboard-grid finance-dashboard-grid finance-spending-grid">
        <article className="hud-panel large"><div className="panel-title"><div><h3>EXPENSES BY CATEGORY</h3></div><span>{spendingBreakdown?.period?.label || "CURRENT"}</span></div><SpendingDonut breakdown={spendingBreakdown} /></article>
        <FixedExpensesPanel data={fixedStatus} onRefresh={onRefresh} isOwner={isOwner} />
        <article className="hud-panel large"><div className="panel-title"><div><h3>RECENT EXPENSES</h3></div><span>{recentExpenses.length}</span></div>{recentExpenses.length ? <div className="finance-detail-list recent-expense-list">{recentExpenses.map((item) => <div className="finance-detail-row" key={item.id || `${item.transaction_date}-${item.description}-${item.amount}`}><div><strong>{item.description}</strong><span>{item.transaction_date} · {item.category}</span></div><b>{formatCRC(item.amount)}</b></div>)}</div> : <EmptyPanel title="No recent expenses" description="New expenses will appear here." />}</article>
        <CurrencyAlertsPanel alerts={currencyAlerts} onApplied={async () => { await loadSupportingData(); await onRefresh?.(); }} />
        <FinanceInputPanel onSaved={async () => { await loadSupportingData(); await onRefresh?.(); }} />
      </div>}

      {activeTab === "income" && <IncomePanel cycleIncome={cycleIncome} cycleTransactions={cycleTransactions} fixedExpectedIncome={fixedExpectedIncome} extraExpectedIncome={extraExpectedIncome} />}
      {activeTab === "aguinaldo" && <AguinaldoPanel data={aguinaldo} />}

      {detail && <div className="finance-detail-modal-backdrop" onClick={() => setDetail(null)}><article className="hud-panel finance-detail-modal" onClick={(event) => event.stopPropagation()}><div className="panel-title"><div><h3>{detail.title}</h3></div><button className="ghost-button" onClick={() => setDetail(null)}>Close</button></div>{detail.items?.length ? <div className="finance-detail-list">{detail.items.map((item) => <div className="finance-detail-row" key={item.id || `${item.transaction_date}-${item.description}-${item.amount}`}><div><strong>{item.description}</strong><span>{item.transaction_date || "No date"} · {item.balance_side || item.category || item.transaction_type}</span></div><b>{formatCRC(item.amount ?? item.net_amount)}</b></div>)}</div> : <EmptyPanel title="No details" description={detail.empty} />}</article></div>}
    </section>
  );
}
