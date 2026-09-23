import { useEffect, useMemo, useState } from "react";
import { deleteFreeMovement, getFreeMovements, updateFreeMovement } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/DincrDialog";
import DincrFormSheet from "../components/DincrFormSheet";
import { deviceLanguage, localeTag } from "../../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const money = (value) => new Intl.NumberFormat(localeTag(language), { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);

export default function Transactions() {
  const [rows, setRows] = useState([]);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [category, setCategory] = useState("all");
  const [edit, setEdit] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  const [error, setError] = useState("");
  const load = () => getFreeMovements().then(setRows).catch((err) => setError(err.message));
  useEffect(() => { load(); }, []);
  const categories = useMemo(() => [...new Set(rows.map((row) => row.category).filter(Boolean))].sort(), [rows]);
  const filtered = useMemo(() => rows.filter((row) => {
    const text = `${row.description} ${row.category}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (type === "all" || row.transaction_type === type) && (category === "all" || row.category === category);
  }), [rows, query, type, category]);
  const save = async (event) => {
    event.preventDefault();
    try {
      await updateFreeMovement(edit.movement_id, { transaction_date: edit.transaction_date, description: edit.description, amount: Number(edit.amount), transaction_type: edit.transaction_type, category: edit.category, notes: edit.notes || "" });
      setEdit(null); load();
    } catch (err) { setError(err.message); }
  };
  const remove = async () => {
    setDeletingBusy(true);
    try { await deleteFreeMovement(deleting.movement_id); setDeleting(null); load(); }
    catch (err) { setError(err.message); }
    finally { setDeletingBusy(false); }
  };
  return <section>
    <div className="hero"><span>DINCR · FREE</span><h1>{tx("Historial", "History")}</h1><p>{tx("Todos tus movimientos en un solo lugar.", "All your transactions in one place.")}</p></div>
    {error && <div className="panel error">{error}</div>}
    <div className="panel movement-filters"><input placeholder={tx("Buscar descripción o categoría", "Search description or category")} value={query} onChange={(e) => setQuery(e.target.value)}/><select value={type} onChange={(e) => setType(e.target.value)}><option value="all">{tx("Todos los tipos", "All types")}</option><option value="income">{tx("Ingresos", "Income")}</option><option value="expense">{tx("Gastos", "Expenses")}</option></select><select value={category} onChange={(e) => setCategory(e.target.value)}><option value="all">{tx("Todas las categorías", "All categories")}</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></div>
    <div className="panel movement-table"><div className="movement-head"><span>{tx("Fecha", "Date")}</span><span>{tx("Movimiento", "Transaction")}</span><span>{tx("Monto", "Amount")}</span></div>{filtered.length ? filtered.map((row) => <div className="movement-row" key={row.movement_id}><time>{String(row.transaction_date).slice(0, 10)}</time><span><strong>{row.description}</strong><small>{row.transaction_type === "income" ? tx("Ingreso", "Income") : tx("Gasto", "Expense")} · {row.category}</small></span><span><b className={row.transaction_type === "expense" ? "negative" : "positive"}>{row.transaction_type === "expense" ? "−" : "+"}{money(row.amount)}</b>{row.editable && <span className="actions"><button className="dincr-button dincr-button-secondary" type="button" onClick={() => setEdit({ ...row, transaction_date: String(row.transaction_date).slice(0, 10) })}>{tx("Editar", "Edit")}</button><button className="dincr-button dincr-button-danger" type="button" onClick={() => setDeleting(row)}>{tx("Eliminar", "Delete")}</button></span>}</span></div>) : <p>{tx("No hay movimientos con esos filtros.", "No transactions match those filters.")}</p>}</div>
    <DincrFormSheet open={Boolean(edit)} eyebrow={tx("Historial", "History")} title={tx("Editar movimiento", "Edit transaction")} onClose={() => setEdit(null)}>{edit && <form className="form dincr-sheet-form" onSubmit={save}><div className="dincr-compact-fields"><label><span>{tx("Fecha", "Date")}</span><input required type="date" value={edit.transaction_date} onChange={(e) => setEdit({ ...edit, transaction_date:e.target.value })}/></label><label><span>{tx("Descripción", "Description")}</span><input required value={edit.description} onChange={(e) => setEdit({ ...edit, description:e.target.value })}/></label><label><span>{tx("Monto", "Amount")}</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" value={edit.amount} onChange={(e) => setEdit({ ...edit, amount:e.target.value })}/></label><label><span>{tx("Categoría", "Category")}</span><input required value={edit.category} onChange={(e) => setEdit({ ...edit, category:e.target.value })}/></label></div><button className="dincr-button dincr-button-primary">{tx("Guardar cambios", "Save changes")}</button></form>}</DincrFormSheet>
    <ConfirmDialog open={Boolean(deleting)} title={tx("Eliminar movimiento", "Delete transaction")} description={deleting ? tx(`Se eliminará ${deleting.description}. Esta acción no se puede deshacer.`, `${deleting.description} will be deleted. This action cannot be undone.`) : ""} onConfirm={remove} onClose={() => { if (!deletingBusy) setDeleting(null); }} busy={deletingBusy}/>
  </section>;
}
