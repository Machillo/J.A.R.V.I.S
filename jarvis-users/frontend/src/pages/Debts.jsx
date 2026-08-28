import { useEffect, useState } from "react";
import { createDebt, deleteDebt, getDebts, payDebt } from "../services/jarvisApi";

const money = (value) => value === null || value === undefined ? "Sin dato" : new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 }).format(Number(value) || 0);
const emptyForm = { name: "", total_amount: "", remaining_amount: "", monthly_payment: "", interest_rate: "", payment_day: "" };
const optionalNumber = (value) => value === "" ? null : Number(value);

export default function Debts() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const load = () => getDebts().then(setRows);
  useEffect(() => { load(); }, []);

  const submit = async (event) => {
    event.preventDefault();
    await createDebt({
      name: form.name.trim(),
      remaining_amount: Number(form.remaining_amount),
      total_amount: optionalNumber(form.total_amount),
      monthly_payment: optionalNumber(form.monthly_payment),
      interest_rate: optionalNumber(form.interest_rate),
      payment_day: optionalNumber(form.payment_day),
    });
    setForm(emptyForm);
    load();
  };

  const pay = async (id) => {
    const raw = prompt("Monto del pago");
    if (!raw) return;
    await payDebt(id, { amount: Number(raw) });
    load();
  };

  return <section><div className="hero"><h1>Deudas</h1><p>Podés registrar una deuda aunque todavía no conozcás todos sus datos.</p></div><form className="panel form horizontal" onSubmit={submit}><input required placeholder="Nombre" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}/><input required type="number" min="0" placeholder="Saldo pendiente" value={form.remaining_amount} onChange={(e) => setForm({ ...form, remaining_amount: e.target.value })}/><input type="number" min="0" placeholder="Monto original (opcional)" value={form.total_amount} onChange={(e) => setForm({ ...form, total_amount: e.target.value })}/><input type="number" min="0" placeholder="Cuota mensual (opcional)" value={form.monthly_payment} onChange={(e) => setForm({ ...form, monthly_payment: e.target.value })}/><button>Agregar</button></form><div className="panel table">{rows.length === 0 ? <p>No hay deudas registradas.</p> : rows.map((debt) => <div className="row" key={debt.id}><span><strong>{debt.name}</strong><small>{money(debt.remaining_amount)} pendiente · cuota {money(debt.monthly_payment)} · interés {debt.interest_rate === null ? "sin dato" : `${debt.interest_rate}%`}</small></span><span className="actions"><button onClick={() => pay(debt.id)}>Pagar</button><button className="danger" onClick={async () => { if (confirm("¿Eliminar deuda?")) { await deleteDebt(debt.id); load(); } }}>Eliminar</button></span></div>)}</div></section>;
}
