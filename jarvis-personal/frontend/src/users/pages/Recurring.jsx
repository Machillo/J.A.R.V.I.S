import { useEffect, useState } from "react";
import { Plus, Repeat2 } from "lucide-react";
import { createRecurring, deleteRecurring, getRecurring, updateRecurring } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";
import { deviceLanguage, localeTag, tx } from "../../lib/locale";

const language=deviceLanguage();
const copy=(es,en)=>tx(es,en,language);
const money = (value) => new Intl.NumberFormat(localeTag(language), { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);
const empty = { name:"", amount:"", category:"general", item_type:"expense", frequency:"monthly", due_day:"", is_active:true };

export default function Recurring({ plan = "basic" }) {
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

  const activeItems = data?.items?.filter((item) => item.is_active) || [];

  return <section className="content-first-page finva-basic-recurring">
    {plan === "free" && <div className="hero"><span>BASIC 06</span><h1>{copy("Recurrentes","Recurring")}</h1><p>{copy("Servicios, suscripciones, alquiler y otros cobros repetidos.","Services, subscriptions, rent, and other repeating charges.")}</p></div>}
    {error && <div className="panel error">{error}</div>}
    {data && <>
      <article className="basic-recurring-summary"><small>{copy("PRÓXIMOS 30 DÍAS","NEXT 30 DAYS")}</small><strong>{money(data.monthly_expenses)} {copy("comprometidos","committed")}</strong><span>{activeItems.length} {copy("movimientos recurrentes","recurring items")}</span></article>
      <div className="basic-recurring-list">{data.items.length ? data.items.map((item) => <article className={`basic-recurring-item ${item.is_active ? "" : "muted-row"}`} key={item.id}>
        <header><strong>{item.name}</strong><b>{item.item_type === "income" ? "+" : "−"}{money(item.amount)}</b></header>
        <p>{copy("día","day")} {item.due_day || "—"} · {item.frequency}</p>
        <div className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={() => toggle(item)}>{item.is_active ? copy("Pausar","Pause") : copy("Activar","Activate")}</button><button className="finva-button finva-button-danger" type="button" onClick={() => setDeleting(item)}>{copy("Eliminar","Delete")}</button></div>
      </article>) : <p className="panel finva-empty-state">{copy("No tenés movimientos recurrentes.","You have no recurring items.")}</p>}</div>
    </>}
    <button className="finva-add-strip basic-recurring-add" type="button" onClick={() => setCreating(true)}><span><Repeat2 size={20}/></span><div><strong>{copy("Crear recurrente","Create recurring item")}</strong><small>{copy("Ingreso o gasto periódico","Recurring income or expense")}</small></div><Plus size={19}/></button>

    <FinvaFormSheet open={creating} eyebrow={copy("Nuevo recurrente","New recurring item")} title={copy("Agregar recurrente","Add recurring item")} onClose={() => setCreating(false)}>
      <form className="form finva-sheet-form" onSubmit={submit}>
        <div className="finva-compact-fields">
          <label><span>{copy("Nombre","Name")}</span><input required placeholder={copy("Ej. Netflix","E.g. Netflix")} value={form.name} onChange={(e) => setForm({...form,name:e.target.value})}/></label>
          <label><span>{copy("Monto","Amount")}</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="₡0" value={form.amount} onChange={(e) => setForm({...form,amount:e.target.value})}/></label>
          <label><span>{copy("Categoría","Category")}</span><input placeholder={copy("Categoría","Category")} value={form.category} onChange={(e) => setForm({...form,category:e.target.value})}/></label>
          <label><span>{copy("Tipo","Type")}</span><select value={form.item_type} onChange={(e) => setForm({...form,item_type:e.target.value})}><option value="expense">{copy("Gasto","Expense")}</option><option value="income">{copy("Ingreso","Income")}</option></select></label>
          <label><span>{copy("Frecuencia","Frequency")}</span><select value={form.frequency} onChange={(e) => setForm({...form,frequency:e.target.value})}><option value="weekly">{copy("Semanal","Weekly")}</option><option value="biweekly">{copy("Quincenal","Twice monthly")}</option><option value="monthly">{copy("Mensual","Monthly")}</option><option value="quarterly">{copy("Trimestral","Quarterly")}</option><option value="annual">{copy("Anual","Annual")}</option></select></label>
          <label><span>{copy("Día de cobro","Due day")}</span><input type="number" inputMode="numeric" min="1" max="31" placeholder="1–31" value={form.due_day} onChange={(e) => setForm({...form,due_day:e.target.value})}/></label>
        </div>
        <button className="finva-button finva-button-primary">{copy("Guardar recurrente","Save recurring item")}</button>
      </form>
    </FinvaFormSheet>
    <ConfirmDialog open={Boolean(deleting)} title={copy("Eliminar recurrente","Delete recurring item")} description={deleting ? copy(`Se eliminará ${deleting.name} de tus movimientos recurrentes.`, `${deleting.name} will be removed from your recurring items.`) : ""} onConfirm={remove} onClose={() => { if (!busy) setDeleting(null); }} busy={busy}/>
  </section>;
}
