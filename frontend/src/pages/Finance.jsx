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
  createDebt,
  updateDebt,
  deleteDebt,
  getFinanceCycleReport,
  getFixedExpenseStatus,
  getReceivables,
  addReceivableEntry,
  applyReceivablePayment,
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


function ReceivablesPanel({ data, onPaymentSaved }) {
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
            const original = Number(item.original_amount) || 0;
            const paid = Number(item.paid_amount) || 0;
            const pending = Number(item.pending_amount) || 0;
            const progress = original > 0 ? Math.min((paid / original) * 100, 100) : 0;
            const isActive = activeId === item.id;
            const showHistory = historyId === item.id;
            return (
              <div className={`receivable-item ${item.status} ${isActive ? "active" : ""}`} key={item.id}>
                <div className="receivable-item-head"><strong>{item.person_name}</strong><b>{formatCRC(pending)}</b></div>
                <div className="receivable-meta"><span>Total: {formatCRC(original)}</span><span>Pagado: {formatCRC(paid)}</span><span>Pendiente: {formatCRC(pending)}</span></div>
                <div className="receivable-bar"><span style={{ width: `${progress}%` }} /></div>
                <div className="receivable-actions">
                  <button type="button" className="ghost-button" onClick={() => setHistoryId(showHistory ? null : item.id)}>{showHistory ? "Ocultar historial" : "Historial"}</button>
                  {pending > 0 && <button type="button" className="ghost-button receivable-payment-toggle" onClick={() => { if (isActive) resetPayment(); else { setActiveId(item.id); setPaymentAmount(""); setPaymentDate(new Date().toISOString().slice(0, 10)); setMessage(""); setShowAdd(false); } }}>{isActive ? "Cancelar" : "Registrar pago"}</button>}
                </div>

                {showHistory && (
                  <div className="receivable-history">
                    {(item.history || []).length === 0 ? <span>Sin movimientos.</span> : (item.history || []).map((entry) => (
                      <div className={`receivable-history-row ${entry.entry_type}`} key={entry.id}>
                        <div><strong>{entry.description || (entry.entry_type === "payment" ? "Pago" : "Cargo")}</strong><span>{String(entry.entry_date || "").slice(0, 10)}</span></div>
                        <b>{entry.entry_type === "payment" ? "−" : "+"}{formatCRC(entry.amount)}</b>
                      </div>
                    ))}
                  </div>
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

function DebtsPanel({ sortedDebts, debtSort, setDebtSort, onChanged }) {
  const [editingDebt, setEditingDebt] = useState(null);
  const [adding, setAdding] = useState(false);
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
                  <button className="ghost-button" onClick={() => setEditingDebt(debt)}>Editar</button>
                  <button className="ghost-button danger" onClick={() => removeDebt(debt)}>Eliminar</button>
                </div>
              </div>
            );
          })
        )}
      </div>

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
        <ReceivablesPanel data={receivables} onPaymentSaved={async () => { await loadSupportingData(); await onRefresh?.(); }} />

        <article className="hud-panel large">
          <div className="panel-title">
            <div>
              <h3>INGRESOS VS GASTOS</h3>
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
            </div>
            <span>REAL</span>
          </div>
          <CategoryBars data={categoryChartData} />
        </article>

        <FixedExpensesPanel data={fixedStatus} onRefresh={onRefresh} isOwner={isOwner} />

        <DebtsPanel
          sortedDebts={sortedDebts}
          debtSort={debtSort}
          setDebtSort={setDebtSort}
          onChanged={async () => { await loadSupportingData(); await onRefresh?.(); }}
        />

        <article className="hud-panel">
          <div className="panel-title"><div><h3>ALERTAS</h3></div></div>
          <div className="alert-list">
            {alerts.length === 0 ? <EmptyPanel title="Sin alertas críticas" description="Cuando haya riesgo de flujo, deuda o metas, aparecerá aquí." /> : alerts.map((alert, index) => <div className={`alert-item ${alert.level}`} key={index}><AlertTriangle size={18} /><span>{alert.message}</span></div>)}
          </div>
        </article>

        <article className="hud-panel large">
          <div className="panel-title"><div><h3>RECOMENDACIONES</h3></div></div>
          {recommendations.length === 0 ? <EmptyPanel title="Sin recomendaciones todavía" description="Cuando registremos ingresos, gastos, deudas y metas, Jarvis tendrá más contexto." /> : <div className="recommendation-list">{recommendations.map((item, index) => <div className="recommendation-item" key={index}>{item}</div>)}</div>}
        </article>

        <article className="hud-panel">
          <div className="panel-title"><div><h3>DATOS BASE</h3></div></div>
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
