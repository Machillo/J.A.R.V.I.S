import { useEffect, useState } from "react";
import { createTransaction, deleteTransaction, getTransactions } from "../services/jarvisApi";
const today = () => new Date().toISOString().slice(0,10);
const money = (v) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(v) || 0);
export default function Transactions() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ transaction_date: today(), description: "", amount: "", transaction_type: "expense", category: "general", notes: "" });
  const run = async (fn) => { setError(""); try { return await fn(); } catch (err) { setError(err?.message || "No se pudo completar la operación."); return null; } };
  const load = () => run(async () => setRows(await getTransactions()));
  useEffect(() => { load(); }, []);
  const submit = async (e) => { e.preventDefault(); const created = await run(() => createTransaction({ ...form, amount: Number(form.amount) })); if (!created) return; setForm({ ...form, description: "", amount: "", notes: "" }); load(); };
  return <section><div className="hero"><h1>Transacciones</h1><p>Registro manual simple.</p></div>{error && <div className="panel error">{error}</div>}<form className="panel form horizontal" onSubmit={submit}><input type="date" value={form.transaction_date} onChange={(e) => setForm({ ...form, transaction_date: e.target.value })}/><input required placeholder="Descripción" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}/><input required type="number" min="0.01" step="0.01" placeholder="Monto" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })}/><select value={form.transaction_type} onChange={(e) => setForm({ ...form, transaction_type: e.target.value })}><option value="expense">Gasto</option><option value="income">Ingreso</option></select><button>Guardar</button></form><div className="panel table">{rows.map((t) => <div className="row" key={t.id}><span><strong>{t.description}</strong><small>{t.transaction_date} · {t.category}</small></span><span><b>{t.transaction_type === "expense" ? "-" : "+"}{money(t.amount)}</b> <button className="danger" onClick={async () => { const ok = await run(() => deleteTransaction(t.id)); if (ok) load(); }}>×</button></span></div>)}</div></section>;
}
