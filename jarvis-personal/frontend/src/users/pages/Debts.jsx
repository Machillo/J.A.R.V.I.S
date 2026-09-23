import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight, CreditCard, Plus } from "lucide-react";
import { createDebt, deleteDebt, getDebts, payDebt, updateDebt } from "../services/jarvisApi";
import { AmountDialog, ConfirmDialog } from "../components/DincrDialog";
import DincrFormSheet from "../components/DincrFormSheet";
import { deviceLanguage, localeTag } from "../../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => value == null ? tx("Sin dato", "No data") : new Intl.NumberFormat(localeTag(language), { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);
const empty = { name:"", debt_type:"other", total_amount:"", remaining_amount:"", monthly_payment:"", interest_rate:"", term_months:"", payment_day:"", next_payment_date:"" };
const opt = (value) => value === "" ? null : Number(value);
const monthsLeft = (debt) => {
  const balance = Number(debt.remaining_amount) || 0;
  const payment = Number(debt.monthly_payment) || 0;
  const rate = (Number(debt.interest_rate) || 0) / 1200;
  if (!payment) return null;
  if (!rate) return Math.ceil(balance/payment);
  const months = -Math.log(1-rate*balance/payment) / Math.log(1+rate);
  return Number.isFinite(months) && months > 0 ? Math.ceil(months) : null;
};

function DebtFields({ value, setValue, advanced }) {
  return <div className="dincr-compact-fields">
    <label><span>{tx("Nombre de la deuda", "Debt name")}</span><input required placeholder={tx("Ej. Tarjeta BAC", "E.g. BAC credit card")} value={value.name} onChange={(e) => setValue({...value,name:e.target.value})}/></label>
    {advanced && <label><span>{tx("Tipo", "Type")}</span><select value={value.debt_type} onChange={(e) => setValue({...value,debt_type:e.target.value})}><option value="credit_card">{tx("Tarjeta", "Credit card")}</option><option value="loan">{tx("Préstamo", "Loan")}</option><option value="other">{tx("Otra", "Other")}</option></select></label>}
    <label><span>{tx("Saldo pendiente", "Outstanding balance")}</span><input required type="number" inputMode="decimal" min="0" step="0.01" placeholder="₡0" value={value.remaining_amount} onChange={(e) => setValue({...value,remaining_amount:e.target.value})}/></label>
    <label><span>{tx("Monto original", "Original amount")}</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="₡0" value={value.total_amount} onChange={(e) => setValue({...value,total_amount:e.target.value})}/></label>
    <label><span>{tx("Cuota mensual", "Monthly payment")}</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="₡0" value={value.monthly_payment} onChange={(e) => setValue({...value,monthly_payment:e.target.value})}/></label>
    {advanced && <>
      <label><span>{tx("Interés anual", "Annual interest")}</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="0%" value={value.interest_rate} onChange={(e) => setValue({...value,interest_rate:e.target.value})}/></label>
      <label><span>{tx("Plazo en meses", "Term in months")}</span><input type="number" inputMode="numeric" min="1" placeholder={tx("Ej. 24", "E.g. 24")} value={value.term_months} onChange={(e) => setValue({...value,term_months:e.target.value})}/></label>
      <label><span>{tx("Día de pago", "Payment day")}</span><input type="number" inputMode="numeric" min="1" max="31" placeholder="1–31" value={value.payment_day} onChange={(e) => setValue({...value,payment_day:e.target.value})}/></label>
      <label><span>{tx("Próxima fecha", "Next date")}</span><input type="date" value={value.next_payment_date || ""} onChange={(e) => setValue({...value,next_payment_date:e.target.value})}/></label>
    </>}
  </div>;
}

export default function Debts({ plan = "free" }) {
  const advanced = plan !== "free";
  const [rows,setRows] = useState([]);
  const [form,setForm] = useState(empty);
  const [creating,setCreating] = useState(false);
  const [edit,setEdit] = useState(null);
  const [payment,setPayment] = useState(null);
  const [paymentAmount,setPaymentAmount] = useState("");
  const [deleting,setDeleting] = useState(null);
  const [busyDialog,setBusyDialog] = useState(false);
  const [error,setError] = useState("");
  const [selected,setSelected] = useState(null);

  const run = async (fn) => {
    setError("");
    try { return await fn(); }
    catch (err) { setError(err.message); return null; }
  };
  const load = () => run(async () => setRows(await getDebts()));
  useEffect(() => { load(); }, []);
  const payload = (value) => ({...value,name:value.name.trim(),remaining_amount:Number(value.remaining_amount),total_amount:opt(value.total_amount),monthly_payment:opt(value.monthly_payment),interest_rate:opt(value.interest_rate),term_months:opt(value.term_months),payment_day:opt(value.payment_day),next_payment_date:value.next_payment_date || null});
  const submit = async (event) => {
    event.preventDefault();
    if (await run(() => createDebt(payload(form)))) { setForm(empty); setCreating(false); load(); }
  };
  const save = async (event) => {
    event.preventDefault();
    if (await run(() => updateDebt(edit.id,payload(edit)))) { setEdit(null); load(); }
  };
  const registerPayment = async () => {
    setBusyDialog(true);
    const saved = await run(() => payDebt(payment.id,{amount:Number(paymentAmount)}));
    setBusyDialog(false);
    if (saved) { setPayment(null); setPaymentAmount(""); load(); }
  };
  const removeDebt = async () => {
    setBusyDialog(true);
    const removed = await run(() => deleteDebt(deleting.id));
    setBusyDialog(false);
    if (removed) { setDeleting(null); load(); }
  };

  const totalBalance = rows.reduce((sum, debt) => sum + Number(debt.remaining_amount || 0), 0);

  const freeContent = selected ? (() => {
    const total = Math.max(Number(selected.total_amount) || Number(selected.remaining_amount) || 1, 1);
    const progress = selected.progress_percent ?? Math.min(Math.max((1 - Number(selected.remaining_amount) / total) * 100, 0), 100);
    return <section className="free-screen free-debt-detail">
      <button className="free-back-button" type="button" onClick={() => setSelected(null)}><ArrowLeft size={18}/>{tx("Volver a deudas", "Back to debts")}</button>
      <article className="free-detail-card">
        <span className="free-detail-icon"><CreditCard size={24}/></span><h2>{selected.name}</h2>
        <div className="free-progress-ring" style={{"--progress":`${progress * 3.6}deg`}}><span><strong>{Math.round(progress)}%</strong><small>{tx("pagado", "paid")}</small></span></div>
        <div className="free-detail-values"><span><small>{tx("Pagado", "Paid")}</small><strong>{money(total - Number(selected.remaining_amount || 0))}</strong></span><span><small>{tx("Restante", "Remaining")}</small><strong>{money(selected.remaining_amount)}</strong></span></div>
        <div className="free-detail-meta"><span>{tx("Cuota mensual", "Monthly payment")}<b>{money(selected.monthly_payment)}</b></span><span>{tx("Interés", "Interest")}<b>{Number(selected.interest_rate || 0)}%</b></span></div>
      </article>
      <button className="free-primary-button" type="button" onClick={() => { setPayment(selected); setPaymentAmount(""); }}>{tx("Registrar pago", "Record payment")}</button>
      <button className="free-secondary-button" type="button" onClick={() => setDeleting(selected)}>{tx("Eliminar deuda", "Delete debt")}</button>
    </section>;
  })() : <section className="free-screen free-debts-screen">
    <small className="free-plan-label">{tx("Gratis", "Free")}</small>
    <article className="free-summary-card free-summary-card--red"><small>{tx("DEUDA TOTAL", "TOTAL DEBT")}</small><strong>{money(totalBalance)}</strong><span>{rows.length} {rows.length === 1 ? tx("deuda activa", "active debt") : tx("deudas activas", "active debts")}</span></article>
    {error && <div className="free-error">{error}</div>}
    <div className="free-record-list">{rows.length ? rows.map((debt) => {
      const total = Math.max(Number(debt.total_amount) || Number(debt.remaining_amount) || 1, 1);
      const progress = debt.progress_percent ?? Math.min(Math.max((1 - Number(debt.remaining_amount) / total) * 100, 0), 100);
      return <button className="free-record-card" type="button" key={debt.id} onClick={() => setSelected(debt)}>
        <span><strong>{debt.name}</strong><small>{money(debt.monthly_payment)}/{tx("mes", "month")} · {Math.round(progress)}% {tx("pagado", "paid")}</small><em>{tx("Ver detalle", "View details")}<ChevronRight size={14}/></em></span><b>{money(debt.remaining_amount)}</b>
      </button>;
    }) : <p className="free-empty">{tx("No tenés deudas registradas.", "You have no recorded debts.")}</p>}</div>
    <button className="free-primary-button" type="button" onClick={() => setCreating(true)}><Plus size={18}/>{tx("Agregar deuda", "Add debt")}</button>
  </section>;

  const content = !advanced ? freeContent : <section className="content-first-page dincr-debts-page">
    <div className="hero"><span>{advanced ? "DINCR · BASIC" : "DINCR · FREE"}</span><h1>{tx("Deudas", "Debts")}</h1><p>{advanced ? tx("Gestión completa con tasa, plazo y finalización estimada.", "Complete management with interest, term, and estimated payoff.") : tx("Saldos, pagos y progreso visual, sin recomendaciones.", "Balances, payments, and visual progress without recommendations.")}</p></div>
    {!advanced && <article className="dincr-free-debt-summary"><small>{tx("SALDO TOTAL", "TOTAL BALANCE")}</small><strong>{money(totalBalance)}</strong><span>{rows.length} {rows.length === 1 ? tx("deuda registrada", "recorded debt") : tx("deudas registradas", "recorded debts")}</span></article>}
    {error && <div className="panel error">{error}</div>}
    <button className="dincr-add-strip" type="button" onClick={() => setCreating(true)}><span><CreditCard size={20}/></span><div><strong>{tx("Agregar deuda", "Add debt")}</strong><small>{tx("Registrá una nueva obligación", "Record a new obligation")}</small></div><Plus size={19}/></button>

    <div className="debt-grid content-first-grid">{rows.length ? rows.map((debt) => {
      const total = Math.max(Number(debt.total_amount) || Number(debt.remaining_amount) || 1,1);
      const progress = debt.progress_percent ?? Math.min(Math.max((1-Number(debt.remaining_amount)/total)*100,0),100);
      const months = monthsLeft(debt);
      return <article className="panel debt-card compact-record-card" key={debt.id}>
        <header><span><b>{debt.name}</b>{advanced && <small>{debt.debt_type}</small>}</span><strong>{money(debt.remaining_amount)}</strong></header>
        <progress max="100" value={progress}/>
        <p>{Number(progress).toFixed(1)}% {tx("pagado · cuota", "paid · payment")} {money(debt.monthly_payment)}</p>
        {advanced && <div className="record-meta"><span>{tx("Próximo pago", "Next payment")}: {(debt.next_payment_date || debt.payment_day) ? `${tx("día", "day")} ${debt.payment_day || String(debt.next_payment_date).slice(8,10)}` : tx("sin fecha", "no date")}</span><span>{tx("Finalización", "Payoff")}: {months ? `~${months} ${tx("meses", "months")}` : tx("faltan datos", "missing data")}</span></div>}
        <div className="actions">
          <button className="dincr-button dincr-button-primary" type="button" onClick={() => { setPayment(debt); setPaymentAmount(""); }}>{tx("Registrar pago", "Record payment")}</button>
          {advanced && <button className="dincr-button dincr-button-secondary" type="button" onClick={() => setEdit({...debt})}>{tx("Editar", "Edit")}</button>}
          <button className="dincr-button dincr-button-danger" type="button" onClick={() => setDeleting(debt)}>{tx("Eliminar", "Delete")}</button>
        </div>
      </article>;
    }) : <div className="panel dincr-empty-state">{tx("No tenés deudas registradas.", "You have no recorded debts.")}</div>}</div>

  </section>;

  return <>{content}<DincrFormSheet open={creating} eyebrow={tx("Nueva deuda", "New debt")} title={tx("Agregar deuda", "Add debt")} onClose={() => setCreating(false)}>
      <form className="form dincr-sheet-form" onSubmit={submit}><DebtFields value={form} setValue={setForm} advanced={advanced}/><button className="dincr-button dincr-button-primary">{tx("Guardar deuda", "Save debt")}</button></form>
    </DincrFormSheet>
    <DincrFormSheet open={Boolean(edit)} eyebrow={tx("Deuda", "Debt")} title={tx("Editar deuda", "Edit debt")} onClose={() => setEdit(null)}>
      {edit && <form className="form dincr-sheet-form" onSubmit={save}><DebtFields value={edit} setValue={setEdit} advanced={advanced}/><button className="dincr-button dincr-button-primary">{tx("Guardar cambios", "Save changes")}</button></form>}
    </DincrFormSheet>
    <AmountDialog open={Boolean(payment)} title={tx("Registrar pago", "Record payment")} description={payment ? `Aplicar un pago a ${payment.name}.` : ""} value={paymentAmount} onValueChange={setPaymentAmount} confirmLabel={tx("Registrar pago", "Record payment")} onConfirm={registerPayment} onClose={() => { if (!busyDialog) setPayment(null); }} busy={busyDialog}/>
    <ConfirmDialog open={Boolean(deleting)} title={tx("Eliminar deuda", "Delete debt")} description={deleting ? tx(`Se eliminará ${deleting.name}. Esta acción no se puede deshacer.`, `${deleting.name} will be deleted. This action cannot be undone.`) : ""} onConfirm={removeDebt} onClose={() => { if (!busyDialog) setDeleting(null); }} busy={busyDialog}/>
  </>;
}
