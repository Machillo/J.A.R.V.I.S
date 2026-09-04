import { useEffect, useState } from "react";
import { Banknote, CreditCard, Landmark, Plus, RefreshCw, ShieldCheck, Trash2, WalletCards } from "lucide-react";
import { deleteAccountBalance, getAccountBalances, getRealBalance, saveAccountBalance } from "../services/jarvisApi";

const money = (value, currency = "CRC") => currency === "USD"
  ? `$${Number(value || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;

const TYPES = [
  ["checking", "Cuenta bancaria"], ["savings", "Ahorros"], ["credit_card", "Tarjeta"],
  ["cash", "Efectivo"], ["emergency_fund", "Salvavidas"], ["other", "Otra"],
];

const iconFor = (type) => type === "credit_card" ? CreditCard : type === "cash" ? Banknote : type === "emergency_fund" ? ShieldCheck : Landmark;

export default function FinancialAccounts() {
  const [state, setState] = useState({ loading: true, data: null, reconciliation: null, error: "" });
  const [editing, setEditing] = useState(false);
  const emptyForm = { account_name: "", bank_name: "", account_type: "checking", account_last4: "", currency: "CRC", current_balance: "", annual_interest_rate: "0", include_in_net_worth: true };
  const [form, setForm] = useState(emptyForm);
  const load = async () => {
    setState((old) => ({ ...old, loading: true, error: "" }));
    try {
      const [data, reconciliation] = await Promise.all([getAccountBalances(), getRealBalance()]);
      setState({ loading: false, data, reconciliation, error: "" });
    } catch (error) { setState((old) => ({ ...old, loading: false, error: error.message || "No pude cargar las cuentas." })); }
  };
  useEffect(() => { load(); }, []);
  const save = async (event) => {
    event.preventDefault();
    await saveAccountBalance({ ...form, current_balance: Number(form.current_balance || 0), annual_interest_rate: Number(form.annual_interest_rate || 0), source: "manual_reconciliation" });
    setEditing(false); setForm(emptyForm);
    await load();
  };
  const edit = (item) => { if (item.read_only) return; setForm({ account_name: item.account_name, bank_name: item.bank_name || "", account_type: item.account_type || "checking", account_last4: item.account_last4 || "", currency: item.currency || "CRC", current_balance: item.calculated_balance ?? item.current_balance, annual_interest_rate: item.annual_interest_rate ?? 0, include_in_net_worth: item.include_in_net_worth !== false }); setEditing(true); };
  const remove = async (id) => { if (!window.confirm("¿Ocultar esta cuenta financiera?")) return; await deleteAccountBalance(id); await load(); };
  const items = state.data?.items || [];

  return <section className="financial-accounts-page">
    <div className="hud-panel financial-accounts-hero"><div><span className="strategy-eyebrow">JARVIS LEDGER</span><h2>Cuentas financieras</h2><p>Dónde está realmente tu dinero. Cada saldo alimenta conciliación y patrimonio sin depender de cálculos imaginarios.</p></div><button className="strategy-refresh-btn" onClick={() => setEditing(!editing)}><Plus size={17}/> {editing ? "Cerrar" : "Agregar cuenta"}</button></div>
    <div className="financial-account-kpis"><div className="hud-card"><WalletCards/><span>Saldo real registrado</span><strong>{money(state.data?.total_real_balance)}</strong></div><div className="hud-card"><RefreshCw/><span>Diferencia por conciliar</span><strong>{money(state.reconciliation?.difference)}</strong><small>{state.reconciliation?.leak_alert?.message}</small></div></div>
    {editing && <form className="hud-panel financial-account-form" onSubmit={save}><h3>Registrar o actualizar cuenta</h3><div className="financial-account-fields"><label>Nombre<input required value={form.account_name} onChange={(e) => setForm({...form, account_name:e.target.value})} placeholder="BAC cuenta principal"/></label><label>Institución<input value={form.bank_name} onChange={(e) => setForm({...form, bank_name:e.target.value})} placeholder="BAC"/></label><label>Tipo<select value={form.account_type} onChange={(e) => setForm({...form, account_type:e.target.value})}>{TYPES.map(([value,label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>Últimos 4<input maxLength="4" value={form.account_last4} onChange={(e) => setForm({...form, account_last4:e.target.value.replace(/\D/g,"")})}/></label><label>Moneda<select value={form.currency} onChange={(e) => setForm({...form, currency:e.target.value})}><option>CRC</option><option>USD</option></select></label><label>Saldo actual<input required type="number" step="0.01" value={form.current_balance} onChange={(e) => setForm({...form, current_balance:e.target.value})}/><small>En tarjetas usá saldo negativo para lo adeudado.</small></label><label>Interés anual<input type="number" min="0" step="0.01" value={form.annual_interest_rate} onChange={(e) => setForm({...form, annual_interest_rate:e.target.value})}/><small>Solo proyecta; no aumenta el saldo real.</small></label></div><label className="financial-account-check"><input type="checkbox" checked={form.include_in_net_worth} onChange={(e) => setForm({...form, include_in_net_worth:e.target.checked})}/> Incluir en patrimonio neto</label><button className="primary-action-button" type="submit">Guardar saldo conciliado</button></form>}
    {state.loading ? <div className="hud-panel">Cargando cuentas...</div> : state.error ? <div className="hud-panel strategy-warning">{state.error}</div> : <div className="financial-account-list">{items.length ? items.map((item) => { const Icon=iconFor(item.account_type); const shown=item.calculated_balance ?? item.current_balance; const projection=Number(item.projected_interest_monthly || 0); return <article className="hud-panel financial-account-row" key={item.id}><button className="financial-account-main" onClick={() => edit(item)}><span className="app-list-icon"><Icon size={23}/></span><span><strong>{item.account_name}</strong><small>{item.bank_name || "Sin institución"}{item.account_last4 ? ` · ****${item.account_last4}` : ""} · {item.account_type}</small>{Number(item.annual_interest_rate || 0) > 0 && <small>{Number(item.annual_interest_rate).toFixed(2)}% anual · proyección {money(projection,item.currency)}/mes</small>}</span></button><span className="financial-account-amount"><strong>{money(shown,item.currency)}</strong><small>{item.read_only ? "Solo lectura · ya incluida" : item.movements_since_balance ? `${item.movements_since_balance} movimientos desde el último saldo` : item.include_in_net_worth ? "Incluida en patrimonio" : "Fuera de patrimonio"}</small></span>{item.read_only ? <span/> : <button className="ghost-button danger" onClick={() => remove(item.id)} aria-label="Ocultar cuenta"><Trash2 size={17}/></button>}</article>; }) : <div className="hud-panel"><h3>Todavía no hay cuentas</h3><p>Agregá BAC, MultiMoney, efectivo o Salvavidas con su saldo actual.</p></div>}</div>}
  </section>;
}
