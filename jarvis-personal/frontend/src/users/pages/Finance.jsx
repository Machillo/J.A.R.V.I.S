import { useEffect, useState } from "react";
import { createExpense, createIncome, createOvertime, getExpenses, getIncome, getOvertime } from "../services/jarvisApi";

const money = (v) => new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(v) || 0);
const today = () => new Date().toISOString().slice(0, 10);

export default function Finance() {
  const [income, setIncome] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [ot, setOt] = useState([]);
  const [error, setError] = useState("");
  const [incomeForm, setIncomeForm] = useState({ amount: "", description: "", category: "salario", entry_date: today() });
  const [expenseForm, setExpenseForm] = useState({ amount: "", description: "", category: "general", entry_date: today() });
  const [otForm, setOtForm] = useState({ hours: "", hourly_rate: "", multiplier: 1.5, work_date: today(), notes: "" });

  const run = async (fn) => {
    setError("");
    try { return await fn(); }
    catch (err) { setError(err?.message || "No se pudo completar la operación."); return null; }
  };

  const load = () => run(async () => {
    const [a, b, c] = await Promise.all([getIncome(), getExpenses(), getOvertime()]);
    setIncome(a); setExpenses(b); setOt(c);
  });

  useEffect(() => { load(); }, []);

  const submitIncome = async (e) => {
    e.preventDefault();
    const created = await run(() => createIncome({ ...incomeForm, amount: Number(incomeForm.amount) }));
    if (!created) return;
    setIncome((prev) => [created, ...prev]);
    setIncomeForm({ ...incomeForm, amount: "", description: "" });
  };

  const submitExpense = async (e) => {
    e.preventDefault();
    const created = await run(() => createExpense({ ...expenseForm, amount: Number(expenseForm.amount) }));
    if (!created) return;
    setExpenses((prev) => [created, ...prev]);
    setExpenseForm({ ...expenseForm, amount: "", description: "" });
  };

  const submitOt = async (e) => {
    e.preventDefault();
    const created = await run(() => createOvertime({ ...otForm, hours: Number(otForm.hours), hourly_rate: Number(otForm.hourly_rate), multiplier: Number(otForm.multiplier) }));
    if (!created) return;
    setOt((prev) => [created, ...prev]);
    setOtForm({ ...otForm, hours: "", notes: "" });
  };

  return <section>
    <div className="hero"><h1>Ingresos y gastos</h1><p>Registro básico del mes.</p></div>
    {error && <div className="panel error">{error}</div>}
    <div className="grid3">
      <form className="panel form" onSubmit={submitIncome}><h3>Ingreso</h3><input required type="number" min="0.01" step="0.01" placeholder="Monto" value={incomeForm.amount} onChange={(e) => setIncomeForm({ ...incomeForm, amount: e.target.value })}/><input placeholder="Descripción" value={incomeForm.description} onChange={(e) => setIncomeForm({ ...incomeForm, description: e.target.value })}/><input type="date" value={incomeForm.entry_date} onChange={(e) => setIncomeForm({ ...incomeForm, entry_date: e.target.value })}/><button>Guardar</button></form>
      <form className="panel form" onSubmit={submitExpense}><h3>Gasto</h3><input required type="number" min="0.01" step="0.01" placeholder="Monto" value={expenseForm.amount} onChange={(e) => setExpenseForm({ ...expenseForm, amount: e.target.value })}/><input placeholder="Descripción" value={expenseForm.description} onChange={(e) => setExpenseForm({ ...expenseForm, description: e.target.value })}/><input placeholder="Categoría" value={expenseForm.category} onChange={(e) => setExpenseForm({ ...expenseForm, category: e.target.value })}/><button>Guardar</button></form>
      <form className="panel form" onSubmit={submitOt}><h3>Horas extra</h3><input required type="number" min="0.01" step="0.01" placeholder="Horas" value={otForm.hours} onChange={(e) => setOtForm({ ...otForm, hours: e.target.value })}/><input required type="number" min="0.01" step="0.01" placeholder="Tarifa por hora" value={otForm.hourly_rate} onChange={(e) => setOtForm({ ...otForm, hourly_rate: e.target.value })}/><input type="number" min="0.01" step="0.01" value={otForm.multiplier} onChange={(e) => setOtForm({ ...otForm, multiplier: e.target.value })}/><button>Guardar</button></form>
    </div>
    <div className="grid3 lists"><div className="panel"><h3>Ingresos recientes</h3>{income.slice(0,8).map((x) => <p key={x.id}>{x.description || x.category}<b>{money(x.amount)}</b></p>)}</div><div className="panel"><h3>Gastos recientes</h3>{expenses.slice(0,8).map((x) => <p key={x.id}>{x.description || x.category}<b>{money(x.amount)}</b></p>)}</div><div className="panel"><h3>OT reciente</h3>{ot.slice(0,8).map((x) => <p key={x.id}>{x.hours} h × {x.multiplier}<b>{money(x.amount)}</b></p>)}</div></div>
  </section>;
}
