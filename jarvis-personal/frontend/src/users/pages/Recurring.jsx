import { useEffect, useState } from "react";
import { Plus, Repeat2 } from "lucide-react";
import { createRecurring, deleteRecurring, getRecurring, updateRecurring } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";

const money = (value) => new Intl.NumberFormat("es-CR", { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);
const empty = { name:"", amount:"", category:"general", item_type:"expense", frequency:"monthly", due_day:"", is_active:true };

export default function Recurring() {
  const [data,setData] = useState(null);
  const [form,setForm] = useState(empty);
  const [creating,setCreating] = useState(false);
  const [deleting,setDeleting] = useState(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const load = () => getRecurring().then(setData).catch((err) => setError(err.message));
  useEffect(() => { load(); }, []);

  const submit = async (event) => {
    event.preventDefault();
    try {
      await createRecurring({...form,amount:Number(form.amount),due_day:form.due_day ? Number(form.due_day) : null});
      setForm(empty);
      setCreating(false);
      load();
    } catch (err) { setError(err.message); }
  };
  const toggle = async (item) => {
    try { await updateRecurring(item.id,{...item,is_active:!item.is_active}); load(); }
    catch (err) { setError(err.message); }
  };
  const remove = async () => {
    setBusy(true);
    try { await deleteRecurring(deleting.id); setDeleting(null); load(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return <section className="content-first-page">
    <div className="hero"><span>BASIC 06</span><h1>Recurrentes</h1><p>Servicios, suscripciones, alquiler y otros cobros repetidos.</p></div>
    {error && <div className="panel error">{error}</div>}
    <button className="finva-add-strip" type="button" onClick={() => setCreating(true)}><span><Repeat2 size={20}/></span><div><strong>Agregar recurrente</strong><small>Creá un ingreso o gasto periódico</small></div><Plus size={19}/></button>

    {data && <>
      <div className="kpis compact-kpis"><div className="card"><small>Costo mensual</small><strong>{money(data.monthly_expenses)}</strong></div><div className="card"><small>Costo anual</small><strong>{money(data.annual_expenses)}</strong></div></div>
      <div className="panel table compact-record-list">{data.items.length ? data.items.map((item) => <div className={`row ${item.is_active ? "" : "muted-row"}`} key={item.id}>
        <span><strong>{item.name}</strong><small>{money(item.monthly_amount)}/mes · {money(item.annual_amount)}/año · día {item.due_day || "—"}</small></span>
        <span className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={() => toggle(item)}>{item.is_active ? "Pausar" : "Activar"}</button><button className="finva-button finva-button-danger" type="button" onClick={() => setDeleting(item)}>Eliminar</button></span>
      </div>) : <p className="finva-empty-state">No tenés movimientos recurrentes.</p>}</div>
    </>}

    <FinvaFormSheet open={creating} eyebrow="Nuevo recurrente" title="Agregar recurrente" onClose={() => setCreating(false)}>
      <form className="form finva-sheet-form" onSubmit={submit}>
        <div className="finva-compact-fields">
          <label><span>Nombre</span><input required placeholder="Ej. Netflix" value={form.name} onChange={(e) => setForm({...form,name:e.target.value})}/></label>
          <label><span>Monto</span><input required type="number" inputMode="decimal" min="0.01" placeholder="₡0" value={form.amount} onChange={(e) => setForm({...form,amount:e.target.value})}/></label>
          <label><span>Categoría</span><input placeholder="Categoría" value={form.category} onChange={(e) => setForm({...form,category:e.target.value})}/></label>
          <label><span>Tipo</span><select value={form.item_type} onChange={(e) => setForm({...form,item_type:e.target.value})}><option value="expense">Gasto</option><option value="income">Ingreso</option></select></label>
          <label><span>Frecuencia</span><select value={form.frequency} onChange={(e) => setForm({...form,frequency:e.target.value})}><option value="weekly">Semanal</option><option value="biweekly">Quincenal</option><option value="monthly">Mensual</option><option value="quarterly">Trimestral</option><option value="annual">Anual</option></select></label>
          <label><span>Día de cobro</span><input type="number" inputMode="numeric" min="1" max="31" placeholder="1–31" value={form.due_day} onChange={(e) => setForm({...form,due_day:e.target.value})}/></label>
        </div>
        <button className="finva-button finva-button-primary">Guardar recurrente</button>
      </form>
    </FinvaFormSheet>
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar recurrente" description={deleting ? `Se eliminará ${deleting.name} de tus movimientos recurrentes.` : ""} onConfirm={remove} onClose={() => { if (!busy) setDeleting(null); }} busy={busy}/>
  </section>;
}
