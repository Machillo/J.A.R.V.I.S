import { useEffect, useMemo, useState } from "react";
import { Banknote, Check, ChevronDown, ChevronRight, CreditCard, Landmark, MailSearch, Plus, RefreshCw, ShieldCheck, Trash2, WalletCards, X } from "lucide-react";
import {
  decideEmailCandidate,
  deleteAccountBalance,
  getAccountBalances,
  getEmailMonitorCandidates,
  getRealBalance,
  saveAccountBalance,
} from "../services/jarvisApi";
import { deviceLanguage, localeTag, t } from "../lib/locale";
import { BANKS, findBankInText, resolveBank } from "../lib/bankBranding";
import BankLogo from "../components/BankLogo";

const money = (value, currency = "CRC") => currency === "USD"
  ? `$${Number(value || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : `₡${Math.round(Number(value || 0)).toLocaleString("es-CR")}`;

const TYPES = [
  ["checking", "Cuenta bancaria"], ["savings", "Ahorros"], ["credit_card", "Tarjeta"],
  ["cash", "Efectivo"], ["emergency_fund", "Salvavidas"], ["other", "Otra"],
];

const iconFor = (type) => type === "credit_card" ? CreditCard : type === "cash" ? Banknote : type === "emergency_fund" ? ShieldCheck : Landmark;
const candidateText = (item) => [item.email_sender, item.email_subject, item.description, item.raw_description, item.notes].filter(Boolean).join(" ");
const bankForCandidate = (item) => resolveBank(item.bank || item.institution_code) || findBankInText(candidateText(item));
const candidateCurrency = (item) => String(item.currency || "").toUpperCase() === "USD" ? "USD" : "CRC";
const candidateDate = (item, language) => {
  const value = item.transaction_date || item.email_received_at || item.created_at;
  return value ? new Date(value).toLocaleDateString(localeTag(language), { day: "numeric", month: "short" }) : "";
};

export default function FinancialAccounts({ onFinanceChanged }) {
  const language = deviceLanguage();
  const tr = (key) => t(`accounts.${key}`, language);
  const [state, setState] = useState({ loading: true, data: null, reconciliation: null, error: "" });
  const [emailState, setEmailState] = useState({ loading: true, items: [], error: "" });
  const [selectedBank, setSelectedBank] = useState(null);
  const [decisionId, setDecisionId] = useState(null);
  const [editing, setEditing] = useState(false);
  const emptyForm = { account_name: "", bank_name: "", account_type: "checking", account_last4: "", currency: "CRC", current_balance: "", annual_interest_rate: "0", include_in_net_worth: true };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    setState((old) => ({ ...old, loading: true, error: "" }));
    setEmailState((old) => ({ ...old, loading: true, error: "" }));
    const [accountsResult, emailResult] = await Promise.allSettled([
      Promise.all([getAccountBalances(), getRealBalance()]),
      getEmailMonitorCandidates("", 500),
    ]);
    if (accountsResult.status === "fulfilled") {
      const [data, reconciliation] = accountsResult.value;
      setState({ loading: false, data, reconciliation, error: "" });
    } else {
      setState((old) => ({ ...old, loading: false, error: accountsResult.reason?.message || tr("loadError") }));
    }
    if (emailResult.status === "fulfilled") {
      setEmailState({ loading: false, items: emailResult.value?.items || [], error: "" });
    } else {
      setEmailState({ loading: false, items: [], error: emailResult.reason?.message || tr("emailError") });
    }
  };

  useEffect(() => { load(); }, []);

  const detectedBanks = useMemo(() => BANKS.map((bank) => {
    const items = emailState.items.filter((item) => bankForCandidate(item)?.id === bank.id);
    const pending = items.filter((item) => item.status === "pending" && !item.transaction_id);
    const last4 = [...new Set(items.map((item) => String(item.card_last4 || "").replace(/\D/g, "").slice(-4)).filter(Boolean))];
    return { ...bank, items, pending, last4 };
  }).filter((bank) => bank.items.length > 0), [emailState.items]);

  const save = async (event) => {
    event.preventDefault();
    await saveAccountBalance({ ...form, current_balance: Number(form.current_balance || 0), annual_interest_rate: Number(form.annual_interest_rate || 0), source: "manual_reconciliation" });
    setEditing(false); setForm(emptyForm);
    await load();
  };

  const edit = (item) => {
    if (item.read_only) return;
    setForm({ account_name: item.account_name, bank_name: item.bank_name || "", account_type: item.account_type || "checking", account_last4: item.account_last4 || "", currency: item.currency || "CRC", current_balance: item.calculated_balance ?? item.current_balance, annual_interest_rate: item.annual_interest_rate ?? 0, include_in_net_worth: item.include_in_net_worth !== false });
    setEditing(true);
  };

  const remove = async (id) => {
    if (!window.confirm(tr("hideConfirm"))) return;
    await deleteAccountBalance(id);
    await load();
  };

  const decide = async (item, decision) => {
    setDecisionId(item.id);
    try {
      await decideEmailCandidate({ candidate_id: item.id, decision });
      await load();
      if (decision === "confirm") await onFinanceChanged?.();
    } finally {
      setDecisionId(null);
    }
  };

  const items = state.data?.items || [];
  const activeBank = detectedBanks.find((bank) => bank.id === selectedBank);

  return <section className="financial-accounts-page jarvis-v2-screen financial-accounts-v2">
    <div className="bank-accounts-heading">
      <div><span className="strategy-eyebrow">{tr("eyebrow")}</span><h2>{tr("title")}</h2><p>{tr("intro")}</p></div>
      <button className="bank-add-button" type="button" onClick={() => setEditing(!editing)} aria-label={tr("add")}><Plus size={22}/></button>
    </div>

    <section className="bank-connections-panel">
      <div className="bank-section-title"><div><strong>{tr("detected")}</strong><small>{tr("version")}</small></div><MailSearch size={20}/></div>
      {emailState.loading ? <div className="bank-empty">{tr("recognizing")}</div> :
        emailState.error ? <div className="bank-empty">{emailState.error}</div> :
        detectedBanks.length === 0 ? <div className="bank-empty">{tr("noneDetected")}</div> :
        <div className="bank-detected-list">
          {detectedBanks.map((bank) => {
            const open = selectedBank === bank.id;
            return <div className={`bank-detected-card ${open ? "open" : ""}`} key={bank.id}>
              <button className="bank-detected-summary" type="button" onClick={() => setSelectedBank(open ? null : bank.id)}>
                <BankLogo bank={bank}/>
                <span className="bank-detected-copy">
                  <strong>{bank.name}</strong>
                  <small>{bank.last4.length ? bank.last4.map((last4) => `•••• ${last4}`).join(" · ") : tr("detectedByEmail")}</small>
                  <small>{bank.items.length} {tr("movements")} · {bank.pending.length} {tr("review")}</small>
                </span>
                <span className="bank-pending-count">{bank.pending.length || <Check size={16}/>}</span>
                {open ? <ChevronDown size={20}/> : <ChevronRight size={20}/>}
              </button>
              {open && <div className="bank-movement-list">
                {bank.items.slice(0, 50).map((item) => {
                  const pending = item.status === "pending" && !item.transaction_id;
                  return <article className="bank-movement-row" key={item.id}>
                    <div className="bank-movement-copy">
                      <strong>{item.description || item.email_subject || tr("movement")}</strong>
                      <small>{candidateDate(item, language)}{item.category ? ` · ${item.category}` : ""}{item.card_last4 ? ` · •••• ${item.card_last4}` : ""}</small>
                      <small className={`bank-movement-status status-${item.status}`}>{pending ? tr("pending") : item.status === "rejected" ? tr("rejected") : item.status === "duplicate" ? tr("duplicate") : tr("inFinance")}</small>
                    </div>
                    <div className="bank-movement-side">
                      <strong>{money(item.amount, candidateCurrency(item))}</strong>
                      {pending && <div className="bank-review-actions">
                        <button className="approve" type="button" disabled={decisionId === item.id} onClick={() => decide(item, "confirm")} aria-label={tr("approve")}><Check size={17}/></button>
                        <button className="reject" type="button" disabled={decisionId === item.id} onClick={() => decide(item, "reject")} aria-label={tr("reject")}><X size={17}/></button>
                      </div>}
                    </div>
                  </article>;
                })}
              </div>}
            </div>;
          })}
        </div>}
    </section>

    <div className="financial-account-kpis jarvis-v2-metrics"><div className="jarvis-v2-metric"><WalletCards/><span>{tr("realBalance")}</span><strong>{money(state.data?.total_real_balance)}</strong></div><div className="jarvis-v2-metric"><RefreshCw/><span>{tr("reconcileDifference")}</span><strong>{money(state.reconciliation?.difference)}</strong><small>{state.reconciliation?.leak_alert?.message}</small></div></div>

    {editing && <form className="hud-panel financial-account-form" onSubmit={save}><h3>Registrar o actualizar cuenta</h3><div className="financial-account-fields"><label>Nombre<input required value={form.account_name} onChange={(e) => setForm({...form, account_name:e.target.value})} placeholder="BAC cuenta principal"/></label><label>Institución<input value={form.bank_name} onChange={(e) => setForm({...form, bank_name:e.target.value})} placeholder="BAC"/></label><label>Tipo<select value={form.account_type} onChange={(e) => setForm({...form, account_type:e.target.value})}>{TYPES.map(([value,label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>Últimos 4<input maxLength="4" value={form.account_last4} onChange={(e) => setForm({...form, account_last4:e.target.value.replace(/\D/g,"")})}/></label><label>Moneda<select value={form.currency} onChange={(e) => setForm({...form, currency:e.target.value})}><option>CRC</option><option>USD</option></select></label><label>Saldo actual<input required type="number" step="0.01" value={form.current_balance} onChange={(e) => setForm({...form, current_balance:e.target.value})}/><small>En tarjetas usá saldo negativo para lo adeudado.</small></label><label>Interés anual<input type="number" min="0" step="0.01" value={form.annual_interest_rate} onChange={(e) => setForm({...form, annual_interest_rate:e.target.value})}/><small>Solo proyecta; no aumenta el saldo real.</small></label></div><label className="financial-account-check"><input type="checkbox" checked={form.include_in_net_worth} onChange={(e) => setForm({...form, include_in_net_worth:e.target.checked})}/> Incluir en patrimonio neto</label><button className="primary-action-button" type="submit">Guardar saldo conciliado</button></form>}

    <section className="bank-ledger-section">
      <div className="bank-section-title"><div><strong>{tr("manual")}</strong><small>{tr("manualHelp")}</small></div></div>
      {state.loading ? <div className="bank-empty">{tr("loading")}</div> : state.error ? <div className="bank-empty">{state.error}</div> : <div className="financial-account-list jarvis-v2-group">{items.length ? items.map((item) => { const Icon=iconFor(item.account_type); const shown=item.calculated_balance ?? item.current_balance; const projection=Number(item.projected_interest_monthly || 0); return <article className="financial-account-row financial-account-row-v2" key={item.id}><button className="financial-account-main" onClick={() => edit(item)}><span className="app-list-icon"><Icon size={23}/></span><span><strong>{item.account_name}</strong><small>{item.bank_name || "Sin institución"}{item.account_last4 ? ` · ****${item.account_last4}` : ""} · {item.account_type}</small>{Number(item.annual_interest_rate || 0) > 0 && <small>{Number(item.annual_interest_rate).toFixed(2)}% anual · proyección {money(projection,item.currency)}/mes</small>}</span></button><span className="financial-account-amount"><strong>{money(shown,item.currency)}</strong><small>{item.read_only ? "Solo lectura · ya incluida" : item.movements_since_balance ? `${item.movements_since_balance} movimientos desde el último saldo` : item.include_in_net_worth ? "Incluida en patrimonio" : "Fuera de patrimonio"}</small></span>{item.read_only ? <span/> : <button className="ghost-button danger" onClick={() => remove(item.id)} aria-label="Ocultar cuenta"><Trash2 size={17}/></button>}</article>; }) : <div className="bank-empty">{tr("noManual")}</div>}</div>}
    </section>
  </section>;
}
