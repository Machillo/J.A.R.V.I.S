import { Building2, Check, CheckCircle2, Mail, Pencil, RefreshCw, ShieldCheck, Unplug, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Browser } from "@capacitor/browser";
import { App } from "@capacitor/app";
import {
  connectVipGmail,
  disconnectVipGmail,
  acceptVipGmailCandidate,
  getVipGmailEmails,
  getVipGmailStatus,
  getVipFinancialIdentity,
  confirmVipFinancialAccount,
  rejectVipGmailCandidate,
  syncVipGmail,
} from "../services/jarvisApi";
import { tx } from "../../lib/locale";

export default function GmailAutomation() {
  const [gmail, setGmail] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [emails, setEmails] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [editing, setEditing] = useState(null);
  const [identity, setIdentity] = useState({ items: [], summary: {} });

  const load = useCallback(async () => {
    try {
      const [status, inbox, accounts] = await Promise.all([
        getVipGmailStatus(), getVipGmailEmails(filter), getVipFinancialIdentity(),
      ]);
      setGmail(status); setEmails(inbox?.items || []); setIdentity(accounts || { items: [], summary: {} });
    }
    catch (err) { setError(err.message || tx("No se pudo consultar Gmail.", "Couldn’t check Gmail.")); }
  }, [filter]);

  const review = async (item, action, corrections = null) => {
    setBusy(`${action}-${item.candidate_id}`); setError(""); setMessage("");
    try {
      if (action === "reject") await rejectVipGmailCandidate(item.candidate_id);
      else await acceptVipGmailCandidate(item.candidate_id, corrections);
      setEditing(null);
      setMessage(action === "reject" ? tx("Correo descartado.", "Email dismissed.") : item.is_internal_transfer ? tx("Transferencia interna confirmada sin contarla como gasto o ingreso.", "Internal transfer confirmed without counting it as income or expense.") : tx("Movimiento guardado.", "Transaction saved."));
      await load();
    } catch (err) { setError(err.message || tx("No se pudo revisar el correo.", "Couldn’t review the email.")); }
    finally { setBusy(""); }
  };

  const confirmAccount = async (item, ownershipStatus) => {
    setBusy(`account-${item.id}`); setError(""); setMessage("");
    try {
      await confirmVipFinancialAccount(item.id, ownershipStatus);
      setMessage(ownershipStatus === "own" ? tx("Cuenta confirmada como propia.", "Account confirmed as yours.") : tx("Cuenta marcada como ajena.", "Account marked as not yours."));
      await load();
    } catch (err) { setError(err.message || tx("No se pudo confirmar la cuenta.", "Couldn’t confirm the account.")); }
    finally { setBusy(""); }
  };

  useEffect(() => {
    load();
    const refresh = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", refresh);
    let appUrlListener;
    App.addListener("appUrlOpen", async ({ url }) => {
      if (!url?.startsWith("com.finva.app://gmail/callback")) return;
      try { await Browser.close(); } catch { /* El navegador ya puede estar cerrado. */ }
      await load();
    }).then((listener) => { appUrlListener = listener; });
    return () => {
      document.removeEventListener("visibilitychange", refresh);
      appUrlListener?.remove();
    };
  }, [load]);

  const connect = async () => {
    setBusy("connect"); setError(""); setMessage("");
    try {
      const response = await connectVipGmail();
      if (!response?.authorization_url) throw new Error(tx("Google no devolvió una dirección de autorización.", "Google did not return an authorization URL."));
      await Browser.open({ url: response.authorization_url, presentationStyle: "popover" });
    } catch (err) { setError(err.message || tx("No se pudo abrir Google.", "Couldn’t open Google.")); }
    finally { setBusy(""); }
  };

  const sync = async () => {
    setBusy("sync"); setError(""); setMessage("");
    try {
      const result = await syncVipGmail();
      await load();
      setMessage(tx(`Listo: ${result.auto_saved || 0} movimientos nuevos y ${result.pending || 0} por revisar.`, `Done: ${result.auto_saved || 0} new transactions and ${result.pending || 0} to review.`));
    } catch (err) { setError(err.message || tx("No se pudo actualizar Gmail.", "Couldn’t refresh Gmail.")); }
    finally { setBusy(""); }
  };

  const disconnect = async () => {
    setBusy("disconnect"); setError(""); setMessage("");
    try {
      await disconnectVipGmail();
      setGmail({ connected: false, status: "disconnected" });
      setMessage(tx("Gmail quedó desconectado de FINVA.", "Gmail was disconnected from FINVA."));
    } catch (err) { setError(err.message || tx("No se pudo desconectar Gmail.", "Couldn’t disconnect Gmail.")); }
    finally { setBusy(""); }
  };

  return <section className="mobile-page gmail-automation-page">
    <div className="mobile-page-heading">
      <p className="eyebrow">{tx("Automatización VIP", "VIP automation")}</p>
      <h1>{tx("Movimientos desde Gmail", "Transactions from Gmail")}</h1>
      <span>{tx("FINVA importa notificaciones bancarias de la cuenta que autoricés.", "FINVA imports bank notifications from the account you authorize.")}</span>
    </div>
    <article className={`gmail-connection-card ${gmail?.needs_reauthorization ? "needs-attention" : ""}`}>
      <div className="gmail-connection-heading"><span><Mail size={21}/></span><div><strong>{tx("Tu correo bancario", "Your banking email")}</strong><small>{tx("Permiso individual · solo lectura", "Individual permission · read only")}</small></div></div>
      <div className="gmail-privacy-note"><ShieldCheck size={19}/><p>{tx("Cada usuario conecta únicamente su propio Gmail. FINVA no puede enviar, modificar ni borrar correos.", "Each user connects only their own Gmail. FINVA cannot send, modify, or delete emails.")}</p></div>
      {!gmail?.connected ? <>
        <p>{gmail?.needs_reauthorization ? tx("El permiso venció o fue revocado. Reconectalo para continuar.", "Permission expired or was revoked. Reconnect to continue.") : tx("Conectá el Gmail donde recibís las notificaciones de tus bancos.", "Connect the Gmail account where you receive bank notifications.")}</p>
        <button type="button" className="finva-button finva-button-primary" disabled={Boolean(busy)} onClick={connect}>{busy === "connect" ? tx("Abriendo Google…", "Opening Google…") : gmail?.needs_reauthorization ? tx("Reconectar Gmail", "Reconnect Gmail") : tx("Conectar mi Gmail", "Connect my Gmail")}</button>
      </> : <>
        <div className="gmail-connection-status"><CheckCircle2 size={18}/><span><strong>{gmail.google_email}</strong><small>{gmail.automatic_updates ? tx("Lectura automática activa", "Automatic reading active") : tx("Correo conectado", "Email connected")}</small></span></div>
        {gmail.pending > 0 && <p>{gmail.pending} {tx("movimiento(s) necesitan revisión.", "transaction(s) need review.")}</p>}
        <div className="gmail-connection-actions"><button type="button" disabled={Boolean(busy)} onClick={sync}><RefreshCw size={16}/>{busy === "sync" ? tx("Actualizando…", "Refreshing…") : tx("Actualizar ahora", "Refresh now")}</button><button type="button" className="danger" disabled={Boolean(busy)} onClick={disconnect}><Unplug size={16}/>{tx("Desconectar", "Disconnect")}</button></div>
      </>}
    </article>
    {gmail?.connected && identity.items.length > 0 && <section className="gmail-identity" aria-label={tx("Cuentas detectadas", "Detected accounts")}>
      <header><div><p className="eyebrow">{tx("Tu mapa financiero", "Your financial map")}</p><h2>{tx("Cuentas detectadas", "Detected accounts")}</h2></div><span>{identity.summary?.pending || 0} {tx("pendientes", "pending")}</span></header>
      <p>{tx("Confirmá cuáles cuentas son tuyas. FINVA no incluirá una cuenta detectada en tu patrimonio sin tu confirmación.", "Confirm which accounts are yours. FINVA won’t include a detected account in your net worth without your confirmation.")}</p>
      <div className="gmail-identity-list">{identity.items.map((item) => <article key={item.id}>
        <span className="gmail-identity-icon"><Building2 size={19}/></span>
        <div><strong>{item.account_name}</strong><small>{item.bank_name} · {item.institution_country} · {item.currency}</small></div>
        {item.ownership_status === "pending" ? <div className="gmail-account-actions"><button type="button" disabled={Boolean(busy)} onClick={() => confirmAccount(item, "not_mine")}>{tx("No es mía", "Not mine")}</button><button type="button" className="primary" disabled={Boolean(busy)} onClick={() => confirmAccount(item, "own")}>{tx("Es mía", "It’s mine")}</button></div> : <span className={`gmail-ownership-state ${item.ownership_status}`}>{item.ownership_status === "own" ? tx("Cuenta propia", "Owned account") : tx("Cuenta ajena", "Not owned")}</span>}
      </article>)}</div>
    </section>}
    {gmail?.connected && <section className="gmail-inbox" aria-label={tx("Correos financieros", "Financial emails")}>
      <header><div><p className="eyebrow">{tx("Bandeja financiera", "Financial inbox")}</p><h2>{tx("Correos recibidos", "Received emails")}</h2></div><span>{emails.length}</span></header>
      <div className="gmail-inbox-tabs">
        <button type="button" className={filter === "pending" ? "active" : ""} onClick={() => setFilter("pending")}>{tx("Por revisar", "To review")}</button>
        <button type="button" className={filter === "" ? "active" : ""} onClick={() => setFilter("")}>{tx("Todos", "All")}</button>
      </div>
      {!emails.length && <div className="gmail-inbox-empty"><Mail size={25}/><strong>{filter ? tx("No hay correos por revisar", "No emails to review") : tx("Todavía no hay correos financieros", "No financial emails yet")}</strong><small>{tx("Cuando FINVA detecte un movimiento bancario aparecerá acá.", "When FINVA detects a bank transaction, it will appear here.")}</small></div>}
      <div className="gmail-email-list">{emails.map((item) => {
        const pending = item.review_status === "pending";
        const edit = editing?.candidate_id === item.candidate_id;
        return <article className="gmail-email-card" key={item.candidate_id || item.email_id}>
          <div className="gmail-email-meta"><span>{item.bank || tx("Banco", "Bank")}</span><time>{item.received_at ? new Date(item.received_at).toLocaleDateString() : ""}</time></div>
          <strong>{item.subject || item.description || tx("Movimiento bancario", "Bank transaction")}</strong>
          <small>{item.sender}</small>
          {item.source_type === "statement" && <p className="gmail-resolution-note">{tx("Detectado en un estado de cuenta PDF. Revisalo igual que cualquier otro movimiento antes de guardarlo.", "Detected in a PDF statement. Review it like any other movement before saving it.")}</p>}
          {item.resolution_reason === "possible_cross_source_match" && <p className="gmail-resolution-note">{tx("Posible coincidencia con una notificación bancaria anterior. FINVA la deja para tu revisión en vez de eliminarla automáticamente.", "Possible match with an earlier bank notification. FINVA leaves it for your review instead of deleting it automatically.")}</p>}
          {item.candidate_id ? edit ? <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); review(item, "accept", { transaction_date: form.get("transaction_date"), description: form.get("description"), amount: Number(form.get("amount")), transaction_type: form.get("transaction_type"), category: form.get("category") }); }} className="gmail-candidate-editor">
            <input name="description" defaultValue={item.description} required aria-label={tx("Descripción", "Description")}/>
            <div><input name="amount" type="number" step="0.01" min="0.01" defaultValue={item.amount} required aria-label={tx("Monto", "Amount")}/><input name="transaction_date" type="date" defaultValue={item.transaction_date} required aria-label={tx("Fecha", "Date")}/></div>
            <div><select name="transaction_type" defaultValue={item.transaction_type}><option value="expense">{tx("Gasto", "Expense")}</option><option value="income">{tx("Ingreso", "Income")}</option><option value="debt_payment">{tx("Pago de deuda", "Debt payment")}</option></select><input name="category" defaultValue={item.category || "general"} required aria-label={tx("Categoría", "Category")}/></div>
            <div className="gmail-review-actions"><button type="button" onClick={() => setEditing(null)}><X size={16}/>{tx("Cancelar", "Cancel")}</button><button className="primary" disabled={Boolean(busy)}><Check size={16}/>{tx("Guardar", "Save")}</button></div>
          </form> : <>
            <div className="gmail-candidate-summary"><span><small>{tx("Descripción", "Description")}</small><b>{item.description}</b></span><span><small>{tx("Monto", "Amount")}</small><b>₡{Number(item.amount || 0).toLocaleString()}</b></span></div>
            {item.is_internal_transfer && <p className="gmail-resolution-note">{tx("FINVA encontró ambas cuentas entre las que confirmaste como propias. Al aceptar, no se registrará como gasto ni ingreso.", "FINVA matched both endpoints to accounts you confirmed as yours. Accepting won’t record income or expense.")}</p>}
            {item.review_status === "duplicate" && <p className="gmail-resolution-note">{tx("FINVA detectó que este correo representa el mismo movimiento que otro registro y evitó contarlo dos veces.", "FINVA detected that this email represents the same movement as another record and avoided double counting it.")}</p>}
            {pending ? <div className="gmail-review-actions"><button type="button" className="reject" disabled={Boolean(busy)} onClick={() => review(item, "reject")}><X size={16}/>{tx("Rechazar", "Reject")}</button>{!item.is_internal_transfer && <button type="button" disabled={Boolean(busy)} onClick={() => setEditing(item)}><Pencil size={16}/>{tx("Corregir", "Edit")}</button>}<button type="button" className="primary" disabled={Boolean(busy)} onClick={() => review(item, "accept")}><Check size={16}/>{item.is_internal_transfer ? tx("Confirmar transferencia", "Confirm transfer") : tx("Aceptar", "Accept")}</button></div> : <span className={`gmail-review-state ${item.review_status}`}>{item.review_status === "confirmed" || item.review_status === "auto_saved" ? tx("Guardado", "Saved") : item.review_status === "rejected" ? tx("Rechazado", "Rejected") : item.review_status === "duplicate" ? tx("Duplicado", "Duplicate") : item.review_status}</span>}
          </> : <p>{item.parse_reason || tx("FINVA no detectó un movimiento en este correo.", "FINVA did not detect a transaction in this email.")}</p>}
        </article>;
      })}</div>
    </section>}
    {message && <p className="success-banner">{message}</p>}
    {error && <p className="onboarding-error">{error}</p>}
  </section>;
}
