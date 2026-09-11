import { useEffect, useState } from "react";
import { createDebt, deleteDebt, getDebts, payDebt, updateDebt } from "../services/jarvisApi";
import { AmountDialog, ConfirmDialog } from "../components/FinvaDialog";

const money = (value) => value == null ? "Sin dato" : new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);
const empty = { name:"", debt_type:"other", total_amount:"", remaining_amount:"", monthly_payment:"", interest_rate:"", term_months:"", payment_day:"", next_payment_date:"" };
const opt = (value) => value === "" ? null : Number(value);
const monthsLeft = (debt) => {
  const balance = Number(debt.remaining_amount) || 0;
  const payment = Number(debt.monthly_payment) || 0;
  const rate = (Number(debt.interest_rate) || 0) / 1200;
  if (!payment) return null;
  if (!rate) return Math.ceil(balance / payment);
  const months = -Math.log(1 - rate * balance / payment) / Math.log(1 + rate);
  return Number.isFinite(months) && months > 0 ? Math.ceil(months) : null;
};

export default function Debts({ plan = "free" }) {
  const advanced = plan !== "free";
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(empty);
  const [edit, setEdit] = useState(null);
  const [payment, setPayment] = useState(null);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [busyDialog, setBusyDialog] = useState(false);
  const [error, setError] = useState("");

  const run = async (fn) => {
    setError("");
    try { return await fn(); }
    catch (err) { setError(err.message); return null; }
  };
  const load = () => run(async () => setRows(await getDebts()));
  useEffect(() => { load(); }, []);

  const payload = (value) => ({
    ...value,
    name:value.name.trim(),
    remaining_amount:Number(value.remaining_amount),
    total_amount:opt(value.total_amount),
    monthly_payment:opt(value.monthly_payment),
    interest_rate:opt(value.interest_rate),
    term_months:opt(value.term_months),
    payment_day:opt(value.payment_day),
    next_payment_date:value.next_payment_date || null,
  });

  const submit = async (event) => {
    event.preventDefault();
    if (await run(() => createDebt(payload(form)))) { setForm(empty); load(); }
  };
  const save = async (event) => {
    event.preventDefault();
    if (await run(() => updateDebt(edit.id, payload(edit)))) { setEdit(null); load(); }
  };
  const registerPayment = async () => {
    setBusyDialog(true);
    const saved = await run(() => payDebt(payment.id, { amount:Number(paymentAmount) }));
    setBusyDialog(false);
    if (saved) { setPayment(null); setPaymentAmount(""); load(); }
  };
  const removeDebt = async () => {
    setBusyDialog(true);
    const removed = await run(() => deleteDebt(deleting.id));
    setBusyDialog(false);
    if (removed) { setDeleting(null); load(); }
  };
  const fields = (value, set) => <>
    <input required placeholder="Nombre" value={value.name} onChange={(e) => set({...value,name:e.target.value})}/>
    {advanced && <select value={value.debt_type} onChange={(e) => set({...value,debt_type:e.target.value})}><option value="credit_card">Tarjeta</option><option value="loan">Préstamo</option><option value="other">Otra</option></select>}
    <input required type="number" min="0" placeholder="Saldo pendiente" value={value.remaining_amount} onChange={(e) => set({...value,remaining_amount:e.target.value})}/>
    <input type="number" min="0" placeholder="Monto original" value={value.total_amount} onChange={(e) => set({...value,total_amount:e.target.value})}/>
    <input type="number" min="0" placeholder="Cuota mensual" value={value.monthly_payment} onChange={(e) => set({...value,monthly_payment:e.target.value})}/>
    {advanced && <>
      <input type="number" min="0" step="0.01" placeholder="Interés anual %" value={value.interest_rate} onChange={(e) => set({...value,interest_rate:e.target.value})}/>
      <input type="number" min="1" placeholder="Plazo en meses" value={value.term_months} onChange={(e) => set({...value,term_months:e.target.value})}/>
      <input type="number" min="1" max="31" placeholder="Día de pago" value={value.payment_day} onChange={(e) => set({...value,payment_day:e.target.value})}/>
      <input type="date" value={value.next_payment_date || ""} onChange={(e) => set({...value,next_payment_date:e.target.value})}/>
    </>}
  </>;

  return <section>
    <div className="hero"><span>{advanced ? "BASIC 03" : "FREE 04"}</span><h1>Deudas</h1><p>{advanced ? "Gestión completa con tasa, plazo y finalización estimada." : "Saldos, pagos y progreso visual, sin recomendaciones."}</p></div>
    {error && <div className="panel error">{error}</div>}
    <form className="panel form" onSubmit={submit}>{fields(form,setForm)}<button className="finva-button finva-button-primary">Agregar deuda</button></form>
    <div className="debt-grid">{rows.map((debt) => {
      const total = Math.max(Number(debt.total_amount) || Number(debt.remaining_amount) || 1, 1);
      const progress = debt.progress_percent ?? Math.min(Math.max((1 - Number(debt.remaining_amount) / total) * 100, 0), 100);
      const months = monthsLeft(debt);
      return <article className="panel debt-card" key={debt.id}>
        <header><span><b>{debt.name}</b>{advanced && <small>{debt.debt_type}</small>}</span><strong>{money(debt.remaining_amount)}</strong></header>
        <progress max="100" value={progress}/>
        <p>{Number(progress).toFixed(1)}% pagado · cuota {money(debt.monthly_payment)}</p>
        {advanced && <><p>Próximo pago: {(debt.next_payment_date || debt.payment_day) ? `día ${debt.payment_day || String(debt.next_payment_date).slice(8,10)}` : "sin fecha"}</p><p>Finalización básica: {months ? `~${months} meses` : "faltan cuota/tasa válidas"}</p></>}
        <div className="actions">
          <button className="finva-button finva-button-primary" type="button" onClick={() => { setPayment(debt); setPaymentAmount(""); }}>Registrar pago</button>
          {advanced && <button className="finva-button finva-button-secondary" type="button" onClick={() => setEdit({...debt})}>Editar</button>}
          <button className="finva-button finva-button-danger" type="button" onClick={() => setDeleting(debt)}>Eliminar</button>
        </div>
      </article>;
    })}</div>
    {edit && <div className="modal-backdrop"><form className="panel form edit-modal" onSubmit={save}><h3>Editar deuda</h3>{fields(edit,setEdit)}<button className="finva-button finva-button-primary">Guardar cambios</button><button className="finva-button finva-button-ghost" type="button" onClick={() => setEdit(null)}>Cancelar</button></form></div>}
    <AmountDialog open={Boolean(payment)} title="Registrar pago" description={payment ? `Aplicar un pago a ${payment.name}.` : ""} value={paymentAmount} onValueChange={setPaymentAmount} confirmLabel="Registrar pago" onConfirm={registerPayment} onClose={() => { if (!busyDialog) setPayment(null); }} busy={busyDialog}/>
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar deuda" description={deleting ? `Se eliminará ${deleting.name}. Esta acción no se puede deshacer.` : ""} onConfirm={removeDebt} onClose={() => { if (!busyDialog) setDeleting(null); }} busy={busyDialog}/>
  </section>;
}
