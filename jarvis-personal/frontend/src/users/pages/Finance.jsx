import { useCallback, useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, CalendarDays, ChevronDown, Plus, Tag } from "lucide-react";
import { createExpense, createIncome, deleteExpense, deleteIncome, getExpenses, getIncome, updateExpense, updateIncome } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";
import { deviceLanguage, localeTag } from "../../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => new Intl.NumberFormat(localeTag(language), { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);
const today = () => new Date().toISOString().slice(0,10);
const incomeCategories = ["Boleta de pago","Bono","Reembolso","Otros ingresos"];
const expenseCategories = ["Vivienda","Servicios","Internet","Teléfono","Seguros","Comida","Restaurante","Transporte","Gasolina","Entretenimiento","Compras","Salud","Deporte","Servicios personales","Mascotas","Otros"];
const incomeEmpty = () => ({ amount:"", description:"", category:"Salario", entry_date:today() });
const expenseEmpty = () => ({ amount:"", description:"", category:"Compras", entry_date:today() });

function EntryFields({ form, setForm, categories }) {
  return <>
    <label className="entry-amount-field"><span>{tx("Monto", "Amount")}</span><div><b>₡</b><input required inputMode="decimal" type="number" min="0.01" step="0.01" placeholder="0" value={form.amount} onChange={(e) => setForm({...form,amount:e.target.value})}/></div></label>
    <label><span>{tx("Descripción", "Description")}</span><input required placeholder="¿Qué movimiento fue?" value={form.description} onChange={(e) => setForm({...form,description:e.target.value})}/></label>
    <div className="entry-field-row">
      <label><span><Tag size={14}/> {tx("Categoría", "Category")}</span><input list={`${categories[0]}-categories`} placeholder="Categoría" value={form.category} onChange={(e) => setForm({...form,category:e.target.value})}/><datalist id={`${categories[0]}-categories`}>{categories.map((item) => <option key={item} value={item}/>)}</datalist></label>
      <label><span><CalendarDays size={14}/> {tx("Fecha", "Date")}</span><input required type="date" value={form.entry_date} onChange={(e) => setForm({...form,entry_date:e.target.value})}/></label>
    </div>
  </>;
}

function Fold({ id, title, subtitle, total, open, onToggle, children }) {
  return <section className={`finva-fold ${open ? "open" : ""}`}>
    <button className="finva-fold-head" type="button" onClick={() => onToggle(id)} aria-expanded={open}>
      <span className="finva-fold-chevron"><ChevronDown size={18}/></span>
      <span className="finva-fold-copy"><strong>{title}</strong>{subtitle && <small>{subtitle}</small>}</span>
      <b>{total}</b>
    </button>
    {open && <div className="finva-fold-body">{children}</div>}
  </section>;
}

export default function Finance() {
  const [income,setIncome] = useState([]);
  const [expenses,setExpenses] = useState([]);
  const [error,setError] = useState("");
  const [incomeForm,setIncomeForm] = useState(incomeEmpty);
  const [expenseForm,setExpenseForm] = useState(expenseEmpty);
  const [entryKind,setEntryKind] = useState(null);
  const [editing,setEditing] = useState(null);
  const [deleting,setDeleting] = useState(null);
  const [deletingBusy,setDeletingBusy] = useState(false);
  const [openGroups,setOpenGroups] = useState(() => {
    try { return JSON.parse(localStorage.getItem("finva:finance-folds")) || ["income","expenses"]; } catch { return ["income","expenses"]; }
  });

  const toggleGroup = (id) => setOpenGroups((current) => {
    const next = current.includes(id) ? current.filter((item) => item !== id) : [...current,id];
    localStorage.setItem("finva:finance-folds", JSON.stringify(next));
    return next;
  });
  const run = useCallback(async (fn) => {
    setError("");
    try { return await fn(); }
    catch (err) { setError(err?.message || "No se pudo completar la operación."); return null; }
  }, []);
  const load = useCallback(() => run(async () => {
    const [incomeRows,expenseRows] = await Promise.all([getIncome(),getExpenses()]);
    setIncome(incomeRows); setExpenses(expenseRows);
  }), [run]);
  useEffect(() => { load(); }, [load]);

  const submitIncome = async (event) => { event.preventDefault(); if (await run(() => createIncome({...incomeForm,amount:Number(incomeForm.amount)}))) { setIncomeForm(incomeEmpty()); setEntryKind(null); load(); } };
  const submitExpense = async (event) => { event.preventDefault(); if (await run(() => createExpense({...expenseForm,amount:Number(expenseForm.amount)}))) { setExpenseForm(expenseEmpty()); setEntryKind(null); load(); } };
  const remove = async () => { setDeletingBusy(true); const removed=await run(() => deleting.kind === "income" ? deleteIncome(deleting.id) : deleteExpense(deleting.id)); setDeletingBusy(false); if (removed) { setDeleting(null); load(); } };
  const saveEdit = async (event) => { event.preventDefault(); const payload={...editing,amount:Number(editing.amount)}; const saved=await run(() => editing.kind === "income" ? updateIncome(editing.id,payload) : updateExpense(editing.id,payload)); if (saved) { setEditing(null); load(); } };
  const openEdit = (kind,item) => setEditing({ kind,id:item.id,amount:item.amount,description:item.description || item.source || "",category:item.category || (kind === "income" ? "Salario" : "Compras"),entry_date:item.entry_date || String(item.created_at).slice(0,10) });
  const isIncome = entryKind === "income"; const activeForm = isIncome ? incomeForm : expenseForm;
  const incomeTotal = income.reduce((sum,item)=>sum+Number(item.amount||0),0);
  const expenseTotal = expenses.reduce((sum,item)=>sum+Number(item.amount||0),0);

  const rows = (items,kind,tone) => items.length ? items.slice(0,8).map((item) => <div className="finva-fold-row" key={item.id}><span><strong>{item.description || item.category}</strong><small>{item.entry_date} · {item.category}</small></span><span><b className={tone}>{money(item.amount)}</b><span className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={()=>openEdit(kind,item)}>{tx("Editar", "Edit")}</button><button className="finva-button finva-button-danger" type="button" onClick={()=>setDeleting({kind,id:item.id,label:item.description || item.category})}>{tx("Eliminar", "Delete")}</button></span></span></div>) : <p className="finva-empty-state">Todavía no hay movimientos en este grupo.</p>;

  return <section className="finance-page finva-progressive-page">
    <div className="hero"><span>MOVIMIENTOS</span><h1>{tx("Tu dinero día a día", "Your money day by day")}</h1><p>Registrá lo que realmente entra y sale de tus cuentas. Sin proyecciones de salario.</p></div>
    {error && <div className="panel error">{error}</div>}
    <div className="finva-money-summary"><small>{tx("Balance de movimientos", "Transaction balance")}</small><strong>{money(incomeTotal-expenseTotal)}</strong><span>{money(incomeTotal)} ingresado · {money(expenseTotal)} gastado</span></div>

    <div className="entry-quick-actions compact">
      <button className="finva-quick-action income" type="button" onClick={()=>setEntryKind("income")}><span><ArrowDownLeft size={20}/></span><div><strong>{tx("Ingreso", "Income")}</strong><small>Agregar movimiento</small></div><Plus size={18}/></button>
      <button className="finva-quick-action expense" type="button" onClick={()=>setEntryKind("expense")}><span><ArrowUpRight size={20}/></span><div><strong>{tx("Gasto", "Expense")}</strong><small>Agregar movimiento</small></div><Plus size={18}/></button>
    </div>

    <div className="finva-fold-list">
      <Fold id="income" title="Ingresos" subtitle={`${income.length} movimientos`} total={money(incomeTotal)} open={openGroups.includes("income")} onToggle={toggleGroup}>{rows(income,"income","positive")}</Fold>
      <Fold id="expenses" title="Gastos" subtitle={`${expenses.length} movimientos`} total={money(expenseTotal)} open={openGroups.includes("expenses")} onToggle={toggleGroup}>{rows(expenses,"expense","negative")}</Fold>
    </div>

    <FinvaFormSheet open={Boolean(entryKind)} eyebrow="Nuevo movimiento" title={isIncome ? "Agregar ingreso" : "Agregar gasto"} onClose={()=>setEntryKind(null)}>
      <form className={`form finva-sheet-form entry-form ${isIncome ? "income":"expense"}`} onSubmit={isIncome ? submitIncome:submitExpense}><EntryFields form={activeForm} setForm={isIncome ? setIncomeForm:setExpenseForm} categories={isIncome ? incomeCategories:expenseCategories}/>{isIncome && <p className="finva-form-hint">Ingresá el monto real que recibiste según tu boleta o depósito bancario.</p>}<button className={`finva-button ${isIncome ? "finva-button-success":"finva-button-primary"}`}>Guardar {isIncome ? "ingreso":"gasto"}</button></form>
    </FinvaFormSheet>
    <FinvaFormSheet open={Boolean(editing)} eyebrow="Movimiento" title={editing?.kind === "income" ? "Editar ingreso":"Editar gasto"} onClose={()=>setEditing(null)}>{editing && <form className="form finva-sheet-form entry-form" onSubmit={saveEdit}><EntryFields form={editing} setForm={setEditing} categories={editing.kind === "income" ? incomeCategories:expenseCategories}/><button className="finva-button finva-button-primary">{tx("Guardar cambios", "Save changes")}</button></form>}</FinvaFormSheet>
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar movimiento" description={deleting ? `Se eliminará ${deleting.label}. Esta acción no se puede deshacer.`:""} onConfirm={remove} onClose={()=>{if(!deletingBusy)setDeleting(null);}} busy={deletingBusy}/>
  </section>;
}
