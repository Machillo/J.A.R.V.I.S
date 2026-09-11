import { useEffect, useState } from "react";
import { CreditCard, Plus } from "lucide-react";
import { createDebt, deleteDebt, getDebts, payDebt, updateDebt } from "../services/jarvisApi";
import { AmountDialog, ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";

const money = (value) => value == null ? "Sin dato" : new Intl.NumberFormat("es-CR", { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);
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
  return <div className="finva-compact-fields">
    <label><span>Nombre de la deuda</span><input required placeholder="Ej. Tarjeta BAC" value={value.name} onChange={(e) => setValue({...value,name:e.target.value})}/></label>
    {advanced && <label><span>Tipo</span><select value={value.debt_type} onChange={(e) => setValue({...value,debt_type:e.target.value})}><option value="credit_card">Tarjeta</option><option value="loan">Préstamo</option><option value="other">Otra</option></select></label>}
    <label><span>Saldo pendiente</span><input required type="number" inputMode="decimal" min="0" placeholder="₡0" value={value.remaining_amount} onChange={(e) => setValue({...value,remaining_amount:e.target.value})}/></label>
    <label><span>Monto original</span><input type="number" inputMode="decimal" min="0" placeholder="₡0" value={value.total_amount} onChange={(e) => setValue({...value,total_amount:e.target.value})}/></label>
    <label><span>Cuota mensual</span><input type="number" inputMode="decimal" min="0" placeholder="₡0" value={value.monthly_payment} onChange={(e) => setValue({...value,monthly_payment:e.target.value})}/></label>
    {advanced && <>
      <label><span>Interés anual</span><input type="number" inputMode="decimal" min="0" step="0.01" placeholder="0%" value={value.interest_rate} onChange={(e) => setValue({...value,interest_rate:e.target.value})}/></label>
      <label><span>Plazo en meses</span><input type="number" inputMode="numeric" min="1" placeholder="Ej. 24" value={value.term_months} onChange={(e) => setValue({...value,term_months:e.target.value})}/></label>
      <label><span>Día de pago</span><input type="number" inputMode="numeric" min="1" max="31" placeholder="1–31" value={value.payment_day} onChange={(e) => setValue({...value,payment_day:e.target.value})}/></label>
      <label><span>Próxima fecha</span><input type="date" value={value.next_payment_date || ""} onChange={(e) => setValue({...value,next_payment_date:e.target.value})}/></label>
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

  return <section className="content-first-page">
    <div className="hero"><span>{advanced ? "BASIC 03" : "FREE 04"}</span><h1>Deudas</h1><p>{advanced ? "Gestión completa con tasa, plazo y finalización estimada." : "Saldos, pagos y progreso visual, sin recomendaciones."}</p></div>
    {error && <div className="panel error">{error}</div>}
    <button className="finva-add-strip" type="button" onClick={() => setCreating(true)}><span><CreditCard size={20}/></span><div><strong>Agregar deuda</strong><small>Registrá una nueva obligación</small></div><Plus size={19}/></button>

    <div className="debt-grid content-first-grid">{rows.length ? rows.map((debt) => {
      const total = Math.max(Number(debt.total_amount) || Number(debt.remaining_amount) || 1,1);
      const progress = debt.progress_percent ?? Math.min(Math.max((1-Number(debt.remaining_amount)/total)*100,0),100);
      const months = monthsLeft(debt);
      return <article className="panel debt-card compact-record-card" key={debt.id}>
        <header><span><b>{debt.name}</b>{advanced && <small>{debt.debt_type}</small>}</span><strong>{money(debt.remaining_amount)}</strong></header>
        <progress max="100" value={progress}/>
        <p>{Number(progress).toFixed(1)}% pagado · cuota {money(debt.monthly_payment)}</p>
        {advanced && <div className="record-meta"><span>Próximo pago: {(debt.next_payment_date || debt.payment_day) ? `día ${debt.payment_day || String(debt.next_payment_date).slice(8,10)}` : "sin fecha"}</span><span>Finalización: {months ? `~${months} meses` : "faltan datos"}</span></div>}
        <div className="actions">
          <button className="finva-button finva-button-primary" type="button" onClick={() => { setPayment(debt); setPaymentAmount(""); }}>Registrar pago</button>
          {advanced && <button className="finva-button finva-button-secondary" type="button" onClick={() => setEdit({...debt})}>Editar</button>}
          <button className="finva-button finva-button-danger" type="button" onClick={() => setDeleting(debt)}>Eliminar</button>
        </div>
      </article>;
    }) : <div className="panel finva-empty-state">No tenés deudas registradas.</div>}</div>

    <FinvaFormSheet open={creating} eyebrow="Nueva deuda" title="Agregar deuda" onClose={() => setCreating(false)}>
      <form className="form finva-sheet-form" onSubmit={submit}><DebtFields value={form} setValue={setForm} advanced={advanced}/><button className="finva-button finva-button-primary">Guardar deuda</button></form>
    </FinvaFormSheet>
    <FinvaFormSheet open={Boolean(edit)} eyebrow="Deuda" title="Editar deuda" onClose={() => setEdit(null)}>
      {edit && <form className="form finva-sheet-form" onSubmit={save}><DebtFields value={edit} setValue={setEdit} advanced={advanced}/><button className="finva-button finva-button-primary">Guardar cambios</button></form>}
    </FinvaFormSheet>
    <AmountDialog open={Boolean(payment)} title="Registrar pago" description={payment ? `Aplicar un pago a ${payment.name}.` : ""} value={paymentAmount} onValueChange={setPaymentAmount} confirmLabel="Registrar pago" onConfirm={registerPayment} onClose={() => { if (!busyDialog) setPayment(null); }} busy={busyDialog}/>
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar deuda" description={deleting ? `Se eliminará ${deleting.name}. Esta acción no se puede deshacer.` : ""} onConfirm={removeDebt} onClose={() => { if (!busyDialog) setDeleting(null); }} busy={busyDialog}/>
  </section>;
}
