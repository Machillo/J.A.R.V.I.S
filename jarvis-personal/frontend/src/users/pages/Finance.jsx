import { useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, CalendarDays, Tag } from "lucide-react";
import { createExpense, createIncome, deleteExpense, deleteIncome, getExpenses, getIncome, updateExpense, updateIncome } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/FinvaDialog";

const money = (v) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(v) || 0);
const today = () => new Date().toISOString().slice(0, 10);
const incomeCategories = ["Salario", "Horas extra", "Bono", "Reembolso", "Otros ingresos"];
const expenseCategories = ["Vivienda", "Servicios", "Internet", "Teléfono", "Seguros", "Comida", "Restaurante", "Transporte", "Gasolina", "Entretenimiento", "Compras", "Salud", "Deporte", "Servicios personales", "Mascotas", "Otros"];
const incomeEmpty = () => ({ amount: "", description: "", category: "Salario", entry_date: today() });
const expenseEmpty = () => ({ amount: "", description: "", category: "Compras", entry_date: today() });

function EntryFields({ form, setForm, categories }) {
  return <>
    <label className="entry-amount-field"><span>Monto</span><div><b>₡</b><input required inputMode="decimal" type="number" min="0.01" step="0.01" placeholder="0" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })}/></div></label>
    <label><span>Descripción</span><input required placeholder="¿Qué movimiento fue?" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}/></label>
    <div className="entry-field-row">
      <label><span><Tag size={14}/> Categoría</span><input list={`${categories[0]}-categories`} placeholder="Categoría" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}/><datalist id={`${categories[0]}-categories`}>{categories.map((item) => <option key={item} value={item}/>)}</datalist></label>
      <label><span><CalendarDays size={14}/> Fecha</span><input required type="date" value={form.entry_date} onChange={(e) => setForm({ ...form, entry_date: e.target.value })}/></label>
    </div>
  </>;
}

export default function Finance() {
  const [income, setIncome] = useState([]), [expenses, setExpenses] = useState([]), [error, setError] = useState("");
  const [incomeForm, setIncomeForm] = useState(incomeEmpty), [expenseForm, setExpenseForm] = useState(expenseEmpty), [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null), [deletingBusy, setDeletingBusy] = useState(false);
  const [entryKind, setEntryKind] = useState("expense");
  const run = async (fn) => { setError(""); try { return await fn(); } catch (err) { setError(err?.message || "No se pudo completar la operación."); return null; } };
  const load = () => run(async () => { const [a,b] = await Promise.all([getIncome(),getExpenses()]); setIncome(a); setExpenses(b); });
  useEffect(() => { load(); }, []);
  const submitIncome = async (e) => { e.preventDefault(); if (await run(() => createIncome({ ...incomeForm, amount:Number(incomeForm.amount) }))) { setIncomeForm(incomeEmpty()); load(); } };
  const submitExpense = async (e) => { e.preventDefault(); if (await run(() => createExpense({ ...expenseForm, amount:Number(expenseForm.amount) }))) { setExpenseForm(expenseEmpty()); load(); } };
  const remove = async () => { setDeletingBusy(true); const removed = await run(() => deleting.kind === "income" ? deleteIncome(deleting.id) : deleteExpense(deleting.id)); setDeletingBusy(false); if (removed) { setDeleting(null); load(); } };
  const saveEdit = async (e) => { e.preventDefault(); const payload={...editing,amount:Number(editing.amount)}; const saved=await run(()=>editing.kind==="income"?updateIncome(editing.id,payload):updateExpense(editing.id,payload)); if(saved){setEditing(null);load();} };
  const openEdit = (kind,item) => setEditing({ kind,id:item.id,amount:item.amount,description:item.description||item.source||"",category:item.category||(kind==="income"?"Salario":"Compras"),entry_date:item.entry_date||String(item.created_at).slice(0,10) });
  const isIncome = entryKind === "income";
  return <section className="finance-page">
    <div className="hero"><span>MOVIMIENTOS</span><h1>Ingresos y gastos</h1><p>Registrá lo importante en pocos segundos.</p></div>
    {error && <div className="panel error">{error}</div>}
    <div className="entry-segmented" role="tablist" aria-label="Tipo de movimiento">
      <button type="button" className={isIncome ? "active income" : ""} onClick={()=>setEntryKind("income")}><ArrowDownLeft size={18}/> Ingreso</button>
      <button type="button" className={!isIncome ? "active expense" : ""} onClick={()=>setEntryKind("expense")}><ArrowUpRight size={18}/> Gasto</button>
    </div>
    <form className={`panel form entry-form ${isIncome ? "income" : "expense"}`} onSubmit={isIncome ? submitIncome : submitExpense}>
      <div className="entry-form-title"><span>{isIncome ? <ArrowDownLeft size={20}/> : <ArrowUpRight size={20}/>}</span><div><h3>Nuevo {isIncome ? "ingreso" : "gasto"}</h3><small>Completá los datos del movimiento</small></div></div>
      <EntryFields form={isIncome ? incomeForm : expenseForm} setForm={isIncome ? setIncomeForm : setExpenseForm} categories={isIncome ? incomeCategories : expenseCategories}/>
      <button className="entry-save-button">Guardar {isIncome ? "ingreso" : "gasto"}</button>
    </form>
    <div className="grid3 lists">
      <div className="panel"><h3>Ingresos recientes</h3>{income.slice(0,8).map((item)=><div className="row" key={item.id}><span><strong>{item.description||item.category}</strong><small>{item.entry_date} · {item.category}</small></span><span><b>{money(item.amount)}</b><span className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={()=>openEdit("income",item)}>Editar</button><button className="finva-button finva-button-danger" type="button" onClick={()=>setDeleting({kind:"income",id:item.id,label:item.description||item.category})}>Eliminar</button></span></span></div>)}</div>
      <div className="panel"><h3>Gastos recientes</h3>{expenses.slice(0,8).map((item)=><div className="row" key={item.id}><span><strong>{item.description||item.category}</strong><small>{item.entry_date} · {item.category}</small></span><span><b>{money(item.amount)}</b><span className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={()=>openEdit("expense",item)}>Editar</button><button className="finva-button finva-button-danger" type="button" onClick={()=>setDeleting({kind:"expense",id:item.id,label:item.description||item.category})}>Eliminar</button></span></span></div>)}</div>
    </div>
    {editing && <div className="modal-backdrop"><form className="panel form edit-modal" onSubmit={saveEdit}><h3>Editar {editing.kind==="income"?"ingreso":"gasto"}</h3><EntryFields form={editing} setForm={setEditing} categories={editing.kind==="income"?incomeCategories:expenseCategories}/><button className="finva-button finva-button-primary">Guardar cambios</button><button className="finva-button finva-button-ghost" type="button" onClick={()=>setEditing(null)}>Cancelar</button></form></div>}
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar movimiento" description={deleting ? `Se eliminará ${deleting.label}. Esta acción no se puede deshacer.` : ""} onConfirm={remove} onClose={()=>{if(!deletingBusy)setDeleting(null);}} busy={deletingBusy}/>
  </section>;
}
