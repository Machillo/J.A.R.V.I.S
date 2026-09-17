import { useCallback, useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, CalendarDays, ChevronDown, Clock3, Plus, Tag } from "lucide-react";
import { createExpense, createIncome, createOvertime, deleteExpense, deleteIncome, getExpenses, getFinancialSituation, getIncome, getOvertime, updateExpense, updateIncome } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";

const money = (value) => new Intl.NumberFormat("es-CR", { style:"currency", currency:"CRC", maximumFractionDigits:0 }).format(Number(value) || 0);
const today = () => new Date().toISOString().slice(0,10);
const incomeCategories = ["Salario","Horas extra","Bono","Reembolso","Otros ingresos"];
const expenseCategories = ["Vivienda","Servicios","Internet","Teléfono","Seguros","Comida","Restaurante","Transporte","Gasolina","Entretenimiento","Compras","Salud","Deporte","Servicios personales","Mascotas","Otros"];
const incomeEmpty = () => ({ amount:"", description:"", category:"Salario", entry_date:today() });
const expenseEmpty = () => ({ amount:"", description:"", category:"Compras", entry_date:today() });
const overtimeEmpty = () => ({ hours:"", hourly_rate:"", multiplier:"1.5", work_date:today(), notes:"" });

function EntryFields({ form, setForm, categories }) {
  return <>
    <label className="entry-amount-field"><span>Monto</span><div><b>₡</b><input required inputMode="decimal" type="number" min="0.01" step="0.01" placeholder="0" value={form.amount} onChange={(e) => setForm({...form,amount:e.target.value})}/></div></label>
    <label><span>Descripción</span><input required placeholder="¿Qué movimiento fue?" value={form.description} onChange={(e) => setForm({...form,description:e.target.value})}/></label>
    <div className="entry-field-row">
      <label><span><Tag size={14}/> Categoría</span><input list={`${categories[0]}-categories`} placeholder="Categoría" value={form.category} onChange={(e) => setForm({...form,category:e.target.value})}/><datalist id={`${categories[0]}-categories`}>{categories.map((item) => <option key={item} value={item}/>)}</datalist></label>
      <label><span><CalendarDays size={14}/> Fecha</span><input required type="date" value={form.entry_date} onChange={(e) => setForm({...form,entry_date:e.target.value})}/></label>
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
  const [overtime,setOvertime] = useState([]);
  const [error,setError] = useState("");
  const [incomeForm,setIncomeForm] = useState(incomeEmpty);
  const [expenseForm,setExpenseForm] = useState(expenseEmpty);
  const [overtimeForm,setOvertimeForm] = useState(overtimeEmpty);
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
    const [incomeRows,expenseRows,overtimeRows,situation] = await Promise.all([getIncome(),getExpenses(),getOvertime(),getFinancialSituation()]);
    setIncome(incomeRows); setExpenses(expenseRows); setOvertime(overtimeRows);
    const profileRate = situation?.financial_profile?.hourly_rate;
    if (profileRate) setOvertimeForm((current) => current.hourly_rate ? current : {...current,hourly_rate:String(profileRate)});
  }), [run]);
  useEffect(() => { load(); }, [load]);

  const submitIncome = async (event) => { event.preventDefault(); if (await run(() => createIncome({...incomeForm,amount:Number(incomeForm.amount)}))) { setIncomeForm(incomeEmpty()); setEntryKind(null); load(); } };
  const submitExpense = async (event) => { event.preventDefault(); if (await run(() => createExpense({...expenseForm,amount:Number(expenseForm.amount)}))) { setExpenseForm(expenseEmpty()); setEntryKind(null); load(); } };
  const submitOvertime = async (event) => { event.preventDefault(); const payload={...overtimeForm,hours:Number(overtimeForm.hours),hourly_rate:Number(overtimeForm.hourly_rate),multiplier:Number(overtimeForm.multiplier)}; if (await run(() => createOvertime(payload))) { setOvertimeForm((current)=>({...overtimeEmpty(),hourly_rate:current.hourly_rate})); setEntryKind(null); load(); } };
  const remove = async () => { setDeletingBusy(true); const removed=await run(() => deleting.kind === "income" ? deleteIncome(deleting.id) : deleteExpense(deleting.id)); setDeletingBusy(false); if (removed) { setDeleting(null); load(); } };
  const saveEdit = async (event) => { event.preventDefault(); const payload={...editing,amount:Number(editing.amount)}; const saved=await run(() => editing.kind === "income" ? updateIncome(editing.id,payload) : updateExpense(editing.id,payload)); if (saved) { setEditing(null); load(); } };
  const openEdit = (kind,item) => setEditing({ kind,id:item.id,amount:item.amount,description:item.description || item.source || "",category:item.category || (kind === "income" ? "Salario" : "Compras"),entry_date:item.entry_date || String(item.created_at).slice(0,10) });
  const isIncome = entryKind === "income"; const isOvertime = entryKind === "overtime"; const activeForm = isIncome ? incomeForm : expenseForm;
  const incomeTotal = income.reduce((sum,item)=>sum+Number(item.amount||0),0);
  const expenseTotal = expenses.reduce((sum,item)=>sum+Number(item.amount||0),0);
  const overtimeTotal = overtime.reduce((sum,item)=>sum+Number(item.amount||0),0);

  const rows = (items,kind,tone) => items.length ? items.slice(0,8).map((item) => <div className="finva-fold-row" key={item.id}><span><strong>{item.description || item.category}</strong><small>{item.entry_date} · {item.category}</small></span><span><b className={tone}>{money(item.amount)}</b><span className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={()=>openEdit(kind,item)}>Editar</button><button className="finva-button finva-button-danger" type="button" onClick={()=>setDeleting({kind,id:item.id,label:item.description || item.category})}>Eliminar</button></span></span></div>) : <p className="finva-empty-state">Todavía no hay movimientos en este grupo.</p>;

  return <section className="finance-page finva-progressive-page">
    <div className="hero"><span>MOVIMIENTOS</span><h1>Tu dinero</h1><p>Todo a mano. Abrí solo el grupo que querás revisar.</p></div>
    {error && <div className="panel error">{error}</div>}
    <div className="finva-money-summary"><small>Balance de movimientos</small><strong>{money(incomeTotal-expenseTotal)}</strong><span>{money(incomeTotal)} ingresado · {money(expenseTotal)} gastado</span></div>

    <div className="entry-quick-actions compact">
      <button className="finva-quick-action income" type="button" onClick={()=>setEntryKind("income")}><span><ArrowDownLeft size={20}/></span><div><strong>Ingreso</strong><small>Agregar movimiento</small></div><Plus size={18}/></button>
      <button className="finva-quick-action expense" type="button" onClick={()=>setEntryKind("expense")}><span><ArrowUpRight size={20}/></span><div><strong>Gasto</strong><small>Agregar movimiento</small></div><Plus size={18}/></button>
      <button className="finva-quick-action overtime" type="button" onClick={()=>setEntryKind("overtime")}><span><Clock3 size={20}/></span><div><strong>Horas extra</strong><small>Registrar horas</small></div><Plus size={18}/></button>
    </div>

    <div className="finva-fold-list">
      <Fold id="income" title="Ingresos" subtitle={`${income.length} movimientos`} total={money(incomeTotal)} open={openGroups.includes("income")} onToggle={toggleGroup}>{rows(income,"income","positive")}</Fold>
      <Fold id="expenses" title="Gastos" subtitle={`${expenses.length} movimientos`} total={money(expenseTotal)} open={openGroups.includes("expenses")} onToggle={toggleGroup}>{rows(expenses,"expense","negative")}</Fold>
      <Fold id="overtime" title="Horas extra" subtitle={`${overtime.length} registros`} total={money(overtimeTotal)} open={openGroups.includes("overtime")} onToggle={toggleGroup}>{overtime.length ? overtime.slice(0,8).map((item)=><div className="finva-fold-row" key={item.id}><span><strong>{Number(item.hours)} horas · ×{Number(item.multiplier)}</strong><small>{String(item.work_date||item.created_at||"").slice(0,10)}{item.notes||item.description ? ` · ${item.notes||item.description}`:""}</small></span><b className="positive">{money(item.amount)}</b></div>) : <p className="finva-empty-state">Todavía no agregaste horas extra.</p>}</Fold>
    </div>

    <FinvaFormSheet open={Boolean(entryKind)} eyebrow="Nuevo movimiento" title={isOvertime ? "Agregar horas extra" : isIncome ? "Agregar ingreso" : "Agregar gasto"} onClose={()=>setEntryKind(null)}>
      {isOvertime ? <form className="form finva-sheet-form entry-form overtime" onSubmit={submitOvertime}><div className="entry-field-row"><label><span>Horas extra trabajadas</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" value={overtimeForm.hours} onChange={(e)=>setOvertimeForm({...overtimeForm,hours:e.target.value})} placeholder="Ej. 3"/></label><label><span>Pago por hora normal</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" value={overtimeForm.hourly_rate} onChange={(e)=>setOvertimeForm({...overtimeForm,hourly_rate:e.target.value})} placeholder="Ej. 2500"/></label></div><div className="entry-field-row"><label><span>Multiplicador</span><select value={overtimeForm.multiplier} onChange={(e)=>setOvertimeForm({...overtimeForm,multiplier:e.target.value})}><option value="1">×1 normal</option><option value="1.5">×1.5</option><option value="2">×2 doble</option><option value="3">×3 triple</option></select></label><label><span><CalendarDays size={14}/> Fecha trabajada</span><input required type="date" value={overtimeForm.work_date} onChange={(e)=>setOvertimeForm({...overtimeForm,work_date:e.target.value})}/></label></div><label><span>Nota opcional</span><input value={overtimeForm.notes} onChange={(e)=>setOvertimeForm({...overtimeForm,notes:e.target.value})} placeholder="Ej. cierre mensual"/></label><p className="finva-form-hint">FINVA calcula: horas × pago por hora × multiplicador.</p><button className="finva-button finva-button-success">Guardar horas extra</button></form> : <form className={`form finva-sheet-form entry-form ${isIncome ? "income":"expense"}`} onSubmit={isIncome ? submitIncome:submitExpense}><EntryFields form={activeForm} setForm={isIncome ? setIncomeForm:setExpenseForm} categories={isIncome ? incomeCategories:expenseCategories}/><button className={`finva-button ${isIncome ? "finva-button-success":"finva-button-primary"}`}>Guardar {isIncome ? "ingreso":"gasto"}</button></form>}
    </FinvaFormSheet>
    <FinvaFormSheet open={Boolean(editing)} eyebrow="Movimiento" title={editing?.kind === "income" ? "Editar ingreso":"Editar gasto"} onClose={()=>setEditing(null)}>{editing && <form className="form finva-sheet-form entry-form" onSubmit={saveEdit}><EntryFields form={editing} setForm={setEditing} categories={editing.kind === "income" ? incomeCategories:expenseCategories}/><button className="finva-button finva-button-primary">Guardar cambios</button></form>}</FinvaFormSheet>
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar movimiento" description={deleting ? `Se eliminará ${deleting.label}. Esta acción no se puede deshacer.`:""} onConfirm={remove} onClose={()=>{if(!deletingBusy)setDeleting(null);}} busy={deletingBusy}/>
  </section>;
}
