import { useEffect, useState } from "react";
import { createGoal, deleteGoal, getGoals } from "../services/jarvisApi";
const money = (v) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(v) || 0);
export default function Goals() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", target_amount: "", current_amount: 0, target_date: "", priority: "medium" });
  const run = async (fn) => { setError(""); try { return await fn(); } catch (err) { setError(err?.message || "No se pudo completar la operación."); return null; } };
  const load = () => run(async () => setRows(await getGoals()));
  useEffect(() => { load(); }, []);
  const submit = async (e) => { e.preventDefault(); const created = await run(() => createGoal({ ...form, target_amount: Number(form.target_amount), current_amount: Number(form.current_amount || 0), target_date: form.target_date || null })); if (!created) return; setForm({ name: "", target_amount: "", current_amount: 0, target_date: "", priority: "medium" }); load(); };
  return <section><div className="hero"><h1>Metas</h1></div>{error && <div className="panel error">{error}</div>}<form className="panel form horizontal" onSubmit={submit}><input required placeholder="Meta" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}/><input required type="number" min="0.01" step="0.01" placeholder="Objetivo" value={form.target_amount} onChange={(e) => setForm({ ...form, target_amount: e.target.value })}/><input type="date" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })}/><button>Agregar</button></form><div className="panel table">{rows.map((g) => <div className="row" key={g.id}><span><strong>{g.name}</strong><small>{money(g.current_amount)} / {money(g.target_amount)}</small></span><button className="danger" onClick={async () => { if (confirm("¿Eliminar meta?")) { const ok = await run(() => deleteGoal(g.id)); if (ok) load(); } }}>Eliminar</button></div>)}</div></section>;
}
