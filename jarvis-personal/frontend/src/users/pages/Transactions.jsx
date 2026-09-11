import { useEffect, useMemo, useState } from "react";
import { deleteFreeMovement, getFreeMovements, updateFreeMovement } from "../services/jarvisApi";
import { ConfirmDialog } from "../components/FinvaDialog";
import FinvaFormSheet from "../components/FinvaFormSheet";

const money = (value) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);

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
    <div className="hero"><span>FREE 06</span><h1>Historial</h1><p>Todos tus movimientos en un solo lugar.</p></div>
    {error && <div className="panel error">{error}</div>}
    <div className="panel movement-filters"><input placeholder="Buscar descripción o categoría" value={query} onChange={(e) => setQuery(e.target.value)}/><select value={type} onChange={(e) => setType(e.target.value)}><option value="all">Todos los tipos</option><option value="income">Ingresos</option><option value="expense">Gastos</option></select><select value={category} onChange={(e) => setCategory(e.target.value)}><option value="all">Todas las categorías</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></div>
    <div className="panel movement-table"><div className="movement-head"><span>Fecha</span><span>Movimiento</span><span>Monto</span></div>{filtered.length ? filtered.map((row) => <div className="movement-row" key={row.movement_id}><time>{String(row.transaction_date).slice(0, 10)}</time><span><strong>{row.description}</strong><small>{row.transaction_type === "income" ? "Ingreso" : "Gasto"} · {row.category}</small></span><span><b className={row.transaction_type === "expense" ? "negative" : "positive"}>{row.transaction_type === "expense" ? "−" : "+"}{money(row.amount)}</b>{row.editable && <span className="actions"><button className="finva-button finva-button-secondary" type="button" onClick={() => setEdit({ ...row, transaction_date: String(row.transaction_date).slice(0, 10) })}>Editar</button><button className="finva-button finva-button-danger" type="button" onClick={() => setDeleting(row)}>Eliminar</button></span>}</span></div>) : <p>No hay movimientos con esos filtros.</p>}</div>
    <FinvaFormSheet open={Boolean(edit)} eyebrow="Historial" title="Editar movimiento" onClose={() => setEdit(null)}>{edit && <form className="form finva-sheet-form" onSubmit={save}><div className="finva-compact-fields"><label><span>Fecha</span><input required type="date" value={edit.transaction_date} onChange={(e) => setEdit({ ...edit, transaction_date:e.target.value })}/></label><label><span>Descripción</span><input required value={edit.description} onChange={(e) => setEdit({ ...edit, description:e.target.value })}/></label><label><span>Monto</span><input required type="number" inputMode="decimal" min="0.01" step="0.01" value={edit.amount} onChange={(e) => setEdit({ ...edit, amount:e.target.value })}/></label><label><span>Categoría</span><input required value={edit.category} onChange={(e) => setEdit({ ...edit, category:e.target.value })}/></label></div><button className="finva-button finva-button-primary">Guardar cambios</button></form>}</FinvaFormSheet>
    <ConfirmDialog open={Boolean(deleting)} title="Eliminar movimiento" description={deleting ? `Se eliminará ${deleting.description}. Esta acción no se puede deshacer.` : ""} onConfirm={remove} onClose={() => { if (!deletingBusy) setDeleting(null); }} busy={deletingBusy}/>
  </section>;
}
