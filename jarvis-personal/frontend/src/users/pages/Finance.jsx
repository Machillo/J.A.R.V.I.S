import { useCallback, useEffect, useState } from "react";
import { useSingleFlight } from "../../lib/useSingleFlight";
import { ArrowDownLeft, ArrowUpRight, CalendarDays, ChevronDown, History, Plus, Search, Tag } from "lucide-react";
import { createExpense, createIncome, deleteExpense, deleteIncome, getExpenses, getFreeMovements, getIncome, updateExpense, updateIncome } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";
import { deviceLanguage } from "../../lib/locale";
import { movementPreview } from "./movementPreview";
import TransactionDebts from "../components/TransactionDebts";
import { categoryLabel, categoryValue } from "../../lib/categories";
import { baseCurrency, entryCurrencyPayload, entryFormAmount, formatMoney, latestUserRate } from "../../lib/currency";
import AmountCurrencyField, { OriginalAmount } from "../components/AmountCurrencyField";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

// Stored amounts and totals are in the account's base currency.
const money = (value) => formatMoney(value);
const today = () => new Date().toISOString().slice(0,10);
const incomeCategories = ["Boleta de pago","Bono","Reembolso","Otros ingresos"];
const expenseCategories = ["Vivienda","Servicios","Internet","Teléfono","Seguros","Comida","Restaurante","Transporte","Gasolina","Entretenimiento","Compras","Salud","Deporte","Servicios personales","Mascotas","Otros"];
const incomeEmpty = () => ({ amount:"", currency:baseCurrency(), exchange_rate:"", description:"", category:categoryLabel("Salario"), entry_date:today() });
const expenseEmpty = () => ({ amount:"", currency:baseCurrency(), exchange_rate:"", description:"", category:categoryLabel("Compras"), entry_date:today() });

function EntryFields({ form, setForm, categories, suggestedRate }) {
  return <>
    <AmountCurrencyField form={form} setForm={setForm} suggestedRate={suggestedRate}/>
    <label><span>{tx("Descripción", "Description")}</span><input required placeholder={tx("¿Qué movimiento fue?", "What was this transaction?")} value={form.description} onChange={(e) => setForm({...form,description:e.target.value})}/></label>
    <div className="entry-field-row">
      <label><span><Tag size={14}/> {tx("Categoría", "Category")}</span><input list={`${categories[0]}-categories`} placeholder={tx("Categoría", "Category")} value={form.category} onChange={(e) => setForm({...form,category:e.target.value})}/><datalist id={`${categories[0]}-categories`}>{categories.map((item) => <option key={item} value={categoryLabel(item)}/>)}</datalist></label>
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

export default function Finance({ plan = "basic", onNavigate }) {
  const compact = plan === "free" || plan === "basic" || plan === "vip";
  const [income,setIncome] = useState([]);
  const [expenses,setExpenses] = useState([]);
  const [movementRows,setMovementRows] = useState([]);
  const [error,setError] = useState("");
  const [incomeForm,setIncomeForm] = useState(incomeEmpty);
  const [expenseForm,setExpenseForm] = useState(expenseEmpty);
  const [entryKind,setEntryKind] = useState(null);
  const [editing,setEditing] = useState(null);
  const [deleting,setDeleting] = useState(null);
  const [deletingBusy,setDeletingBusy] = useState(false);
  const [query,setQuery] = useState("");
  const [filter,setFilter] = useState("all");
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
    catch (err) { setError(err?.message || tx("No se pudo completar la operación.", "The operation could not be completed.")); return null; }
  }, []);
  const load = useCallback(() => run(async () => {
    if (compact) {
      setMovementRows(await getFreeMovements());
      return;
    }
    const [incomeRows,expenseRows] = await Promise.all([getIncome(),getExpenses()]);
    setIncome(incomeRows); setExpenses(expenseRows);
  }), [compact, run]);
  useEffect(() => { load(); }, [load]);

  const [once, saving] = useSingleFlight();
  const entryPayload = (form) => ({...form,category:categoryValue(form.category),amount:Number(form.amount),...entryCurrencyPayload(form)});
  const submitIncome = once(async (event) => { event.preventDefault(); if (await run(() => createIncome(entryPayload(incomeForm)))) { setIncomeForm(incomeEmpty()); setEntryKind(null); load(); } });
  const submitExpense = once(async (event) => { event.preventDefault(); if (await run(() => createExpense(entryPayload(expenseForm)))) { setExpenseForm(expenseEmpty()); setEntryKind(null); load(); } });
  const remove = async () => { setDeletingBusy(true); const removed=await run(() => deleting.kind === "income" ? deleteIncome(deleting.id) : deleteExpense(deleting.id)); setDeletingBusy(false); if (removed) { setDeleting(null); load(); } };
  const saveEdit = once(async (event) => { event.preventDefault(); const payload=entryPayload(editing); const saved=await run(() => editing.kind === "income" ? updateIncome(editing.id,payload) : updateExpense(editing.id,payload)); if (saved) { setEditing(null); load(); } });
  const openEdit = (kind,item) => setEditing({ kind,id:item.id,...entryFormAmount(item),description:item.description || item.source || "",category:categoryLabel(item.category || (kind === "income" ? "Salario" : "Compras")),entry_date:item.entry_date || String(item.created_at).slice(0,10) });
  const isIncome = entryKind === "income"; const activeForm = isIncome ? incomeForm : expenseForm;
  const incomeTotal = income.reduce((sum,item)=>sum+Number(item.amount||0),0);
  const expenseTotal = expenses.reduce((sum,item)=>sum+Number(item.amount||0),0);
  const movements = movementPreview(movementRows, query, filter);
  const suggestedRate = latestUserRate([...movementRows, ...income, ...expenses]);

  const rows = (items,kind,tone) => items.length ? items.slice(0,8).map((item) => <div className="finva-fold-row" key={item.id}><span><strong>{item.description || categoryLabel(item.category)}</strong><small>{item.entry_date} · {categoryLabel(item.category)}</small></span><span><b className={tone}>{money(item.amount)}</b><OriginalAmount row={item}/><span className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={()=>openEdit(kind,item)}>{tx("Editar", "Edit")}</button><button className="finva-button finva-button-danger" type="button" onClick={()=>setDeleting({kind,id:item.id,label:item.description || categoryLabel(item.category)})}>{tx("Eliminar", "Delete")}</button></span></span></div>) : <p className="finva-empty-state">{tx("Todavía no hay movimientos en este grupo.","There are no transactions in this group yet.")}</p>;

  const content = compact ? <section className={`free-screen free-movements-screen ${plan !== "free" ? "basic-movements-screen" : ""}`}>
    {/* VIP has no app header, so the tab shows its own title like the other VIP pages. */}
    {plan === "vip" ? <div className="hero"><span>DINCR · VIP</span><h1>{tx("Movimientos", "Transactions")}</h1></div> : <small className="free-plan-label">{plan === "free" ? tx("Gratis", "Free") : "Basic"}</small>}
    {error && <div className="free-error">{error}</div>}
    <label className="free-search"><Search size={18}/><input aria-label={tx("Buscar movimientos", "Search transactions")} placeholder={tx("Buscar movimientos", "Search transactions")} value={query} onChange={(event) => setQuery(event.target.value)}/></label>
    <div className="free-filter-tabs" role="tablist">
      {[['all',tx('Todos','All')],['income',tx('Ingresos','Income')],['expense',tx('Gastos','Expenses')],['debt',tx('Deudas','Debts')]].map(([key,label]) => <button type="button" key={key} className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>{label}</button>)}
    </div>
    {/* Debts: the same list as Plan → Debts (read-only here), then their payments. */}
    {filter === "debt" && <TransactionDebts onManage={onNavigate ? () => onNavigate("debts") : undefined}/>}
    {filter === "debt" && <h2 className="free-list-title">{tx("Pagos de deudas", "Debt payments")}</h2>}
    <div className="free-transaction-list">
      {movements.length ? movements.map((item) => {
        const Row = item.editable ? "button" : "div";
        return <Row className="free-transaction-row" type={item.editable ? "button" : undefined} key={item.movement_id} onClick={item.editable ? () => {
          if (item.origin === "salary" || item.origin === "expense") openEdit(item.origin === "salary" ? "income" : "expense", {
            id: item.source_id, amount: item.amount, original_amount: item.original_amount,
            original_currency: item.original_currency, exchange_rate: item.exchange_rate, description: item.description,
            category: item.category, entry_date: String(item.transaction_date).slice(0, 10),
          });
          else onNavigate?.("transactions");
        } : undefined}>
        <span><strong>{item.description || categoryLabel(item.category) || tx("Movimiento", "Transaction")}</strong><small>{String(item.transaction_date || "").slice(0,10)} · {categoryLabel(item.category)}{!item.editable && ` · ${tx("Solo lectura", "Read only")}`}</small></span>
        <span className="entry-amount-cell"><b className={item.kind}>{item.kind === "income" ? "+" : "−"}{money(item.amount)}</b><OriginalAmount row={item}/></span>
      </Row>;
      }) : <p className="free-empty">{tx("No hay movimientos con esos filtros.", "No transactions match those filters.")}</p>}
    </div>
    {onNavigate && <button className="free-secondary-button" type="button" onClick={() => onNavigate("transactions")}><History size={18}/>{tx("Filtrar y gestionar historial", "Filter and manage history")}</button>}
    <button className="free-primary-button" type="button" onClick={() => setEntryKind("choose")}><Plus size={18}/>{tx("Agregar movimiento", "Add transaction")}</button>
  </section> : <section className="finance-page finva-progressive-page">
    <div className="hero"><span>{tx("MOVIMIENTOS", "TRANSACTIONS")}</span><h1>{tx("Tu dinero día a día", "Your money day by day")}</h1><p>{tx("Registrá lo que realmente entra y sale de tus cuentas. Sin proyecciones de salario.", "Record what actually enters and leaves your accounts, without projected income.")}</p></div>
    {error && <div className="panel error">{error}</div>}
    <div className="finva-money-summary"><small>{tx("Balance de movimientos", "Transaction balance")}</small><strong>{money(incomeTotal-expenseTotal)}</strong><span>{money(incomeTotal)} {tx("ingresado", "received")} · {money(expenseTotal)} {tx("gastado", "spent")}</span></div>

    <div className="entry-quick-actions compact">
      <button className="finva-quick-action income" type="button" onClick={()=>setEntryKind("income")}><span><ArrowDownLeft size={20}/></span><div><strong>{tx("Ingreso", "Income")}</strong><small>{tx("Agregar movimiento", "Add transaction")}</small></div><Plus size={18}/></button>
      <button className="finva-quick-action expense" type="button" onClick={()=>setEntryKind("expense")}><span><ArrowUpRight size={20}/></span><div><strong>{tx("Gasto", "Expense")}</strong><small>{tx("Agregar movimiento", "Add transaction")}</small></div><Plus size={18}/></button>
    </div>

    <div className="finva-fold-list">
      <Fold id="income" title={tx("Ingresos", "Income")} subtitle={`${income.length} ${tx("movimientos", "transactions")}`} total={money(incomeTotal)} open={openGroups.includes("income")} onToggle={toggleGroup}>{rows(income,"income","positive")}</Fold>
      <Fold id="expenses" title={tx("Gastos", "Expenses")} subtitle={`${expenses.length} ${tx("movimientos", "transactions")}`} total={money(expenseTotal)} open={openGroups.includes("expenses")} onToggle={toggleGroup}>{rows(expenses,"expense","negative")}</Fold>
    </div>

  </section>;

  return <>{content}
    <FinvaFormSheet open={Boolean(entryKind)} eyebrow={tx("Nuevo movimiento", "New transaction")} title={entryKind === "choose" ? tx("¿Qué querés registrar?", "What do you want to record?") : isIncome ? tx("Agregar ingreso", "Add income") : tx("Agregar gasto", "Add expense")} onClose={()=>setEntryKind(null)}>
      {entryKind === "choose" ? <div className="free-entry-choices"><button type="button" onClick={() => setEntryKind("income")}><ArrowDownLeft/>{tx("Ingreso", "Income")}</button><button type="button" onClick={() => setEntryKind("expense")}><ArrowUpRight/>{tx("Gasto", "Expense")}</button></div> : <form className={`form finva-sheet-form entry-form ${isIncome ? "income":"expense"}`} onSubmit={isIncome ? submitIncome:submitExpense}><EntryFields form={activeForm} setForm={isIncome ? setIncomeForm:setExpenseForm} categories={isIncome ? incomeCategories:expenseCategories} suggestedRate={suggestedRate}/>{isIncome && <p className="finva-form-hint">{tx("Ingresá el monto real que recibiste según tu boleta o depósito bancario.", "Enter the actual amount received according to your pay stub or bank deposit.")}</p>}<button className={`finva-button ${isIncome ? "finva-button-success":"finva-button-primary"}`}>{isIncome ? tx("Guardar ingreso", "Save income") : tx("Guardar gasto", "Save expense")}</button></form>}
    </FinvaFormSheet>
    <FinvaFormSheet open={Boolean(editing)} eyebrow={tx("Movimiento", "Transaction")} title={editing?.kind === "income" ? tx("Editar ingreso", "Edit income") : tx("Editar gasto", "Edit expense")} onClose={()=>setEditing(null)}>{editing && <form className="form finva-sheet-form entry-form" onSubmit={saveEdit}><EntryFields form={editing} setForm={setEditing} categories={editing.kind === "income" ? incomeCategories:expenseCategories} suggestedRate={suggestedRate}/><button className="finva-button finva-button-primary" disabled={saving}>{tx("Guardar cambios", "Save changes")}</button></form>}</FinvaFormSheet>
    <ConfirmDialog open={Boolean(deleting)} title={tx("Eliminar movimiento", "Delete transaction")} description={deleting ? tx(`Se eliminará ${deleting.label}. Esta acción no se puede deshacer.`, `${deleting.label} will be deleted. This action cannot be undone.`):""} onConfirm={remove} onClose={()=>{if(!deletingBusy)setDeleting(null);}} busy={deletingBusy}/>
  </>;
}
