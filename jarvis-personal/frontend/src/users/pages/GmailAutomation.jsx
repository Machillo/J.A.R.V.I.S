import { Building2, Check, CheckCircle2, Mail, Pencil, RefreshCw, ShieldCheck, Unplug, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Browser } from "@capacitor/browser";
import { App } from "@capacitor/app";
import {
  connectVipGmail,
  acceptVipGmailConsent,
  disconnectVipGmail,
  acceptVipGmailCandidate,
  getVipGmailEmails,
  getVipOwnTransferSuggestions,
  confirmVipOwnTransfer,
  getVipGmailStatus,
  getVipFinancialIdentity,
  confirmVipFinancialAccount,
  rejectVipGmailCandidate,
  syncVipGmail,
} from "../services/jarvisApi";
import { tx } from "../../lib/locale";
import { trackEvent } from "../../lib/telemetry";

export default function GmailAutomation() {
  const [gmail, setGmail] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [emails, setEmails] = useState([]);
  const [transferSuggestions, setTransferSuggestions] = useState([]);
  const [transferReview, setTransferReview] = useState(null);
  const [filter, setFilter] = useState("pending");
  const [editing, setEditing] = useState(null);
  const [identity, setIdentity] = useState({ items: [], summary: {} });
  const [consentAccepted, setConsentAccepted] = useState(false);

  const load = useCallback(async () => {
    try {
      const [status, inbox, accounts] = await Promise.all([
        getVipGmailStatus(), getVipGmailEmails(filter), getVipFinancialIdentity(),
      ]);
      setGmail(status); setEmails(inbox?.items || []); setIdentity(accounts || { items: [], summary: {} });
      const proposed = await getVipOwnTransferSuggestions().catch(() => ({ items: [] }));
      setTransferSuggestions(proposed.items || []);
    }
    catch (err) { setError(err.message || tx("No se pudo consultar Gmail.", "Couldn’t check Gmail.")); }
  }, [filter]);

  const review = async (item, action, corrections = null) => {
    setBusy(`${action}-${item.candidate_id}`); setError(""); setMessage("");
    try {
      if (action === "reject") await rejectVipGmailCandidate(item.candidate_id);
      else await acceptVipGmailCandidate(item.candidate_id, corrections);
      trackEvent("email_candidate_reviewed", {
        decision: action === "reject" ? "rejected" : corrections ? "corrected" : "accepted",
        bank: item.bank || "unknown",
        institution_country: item.institution_country || "unknown",
        source_type: item.source_type || "email",
        is_internal_transfer: Boolean(item.is_internal_transfer),
      });
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
      trackEvent("financial_account_ownership_reviewed", {
        bank: item.bank_name || "unknown",
        institution_country: item.institution_country || "unknown",
        ownership_status: ownershipStatus,
      });
      setMessage(ownershipStatus === "own" ? tx("Cuenta confirmada como propia.", "Account confirmed as yours.") : tx("Cuenta marcada como ajena.", "Account marked as not yours."));
      await load();
    } catch (err) { setError(err.message || tx("No se pudo confirmar la cuenta.", "Couldn’t confirm the account.")); }
    finally { setBusy(""); }
  };

  const confirmTransfer = async () => {
    if (!transferReview?.confirmed) return;
    setBusy("own-transfer"); setError(""); setMessage("");
    try {
      await confirmVipOwnTransfer(
        transferReview.firstId, transferReview.secondId,
        transferReview.needsDirection ? transferReview.unknownDirection : null,
      );
      setTransferReview(null);
      await load();
      setMessage(tx("Ambos avisos quedaron como una transferencia propia, sin sumarse a ingresos ni gastos.", "Both notices are now an own-account transfer, excluded from income and expenses."));
    } catch (err) { setError(err.message || tx("No pudimos confirmar la transferencia.", "Couldn’t confirm the transfer.")); }
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
      if (gmail?.consent?.required) {
        if (!consentAccepted) throw new Error(tx("Debés aceptar la explicación de Email Monitor antes de conectarlo.", "You must accept the Email Monitor explanation before connecting it."));
        await acceptVipGmailConsent(gmail.consent.version);
      }
      const response = await connectVipGmail();
      trackEvent("gmail_connection_started");
      if (!response?.authorization_url) throw new Error(tx("Google no devolvió una dirección de autorización.", "Google did not return an authorization URL."));
      await Browser.open({ url: response.authorization_url, presentationStyle: "popover" });
    } catch (err) { setError(err.message || tx("No se pudo abrir Google.", "Couldn’t open Google.")); }
    finally { setBusy(""); }
  };

  const sync = async () => {
    setBusy("sync"); setError(""); setMessage("");
    try {
      const result = await syncVipGmail();
      trackEvent("gmail_sync_completed", {
        scan_scope: result.scan_scope || "unknown",
        initial_scan_complete: Boolean(result.initial_scan_complete),
        auto_saved: result.auto_saved || 0,
        pending: result.pending || 0,
      });
      await load();
      const progress = result.scan_scope === "year_to_date" && !result.initial_scan_complete
        ? tx(" DINCR continuará recorriendo el resto del año en las próximas actualizaciones.", " DINCR will continue scanning the rest of the year during the next refreshes.")
        : "";
      setMessage(tx(`Listo: ${result.auto_saved || 0} movimientos nuevos y ${result.pending || 0} por revisar.`, `Done: ${result.auto_saved || 0} new transactions and ${result.pending || 0} to review.`) + progress + (result.failed_connections?.length ? tx(" Algunas conexiones necesitan atención.", "Some connections need attention.") : ""));
    } catch (err) {
      setError(err.message || tx("No se pudo actualizar Gmail.", "Couldn’t refresh Gmail."));
      await load();
    }
    finally { setBusy(""); }
  };

  const disconnect = async (connectionId) => {
    setBusy("disconnect"); setError(""); setMessage("");
    try {
      await disconnectVipGmail(connectionId);
      trackEvent("gmail_disconnected");
      await load();
      setMessage(tx("Ese Gmail quedó desconectado de DINCR.", "That Gmail was disconnected from DINCR."));
    } catch (err) { setError(err.message || tx("No se pudo desconectar Gmail.", "Couldn’t disconnect Gmail.")); }
    finally { setBusy(""); }
  };

  // Each bank sends its own notification. Show one review item for a matched
  // own-account transfer while retaining both source records in the backend.
  const inboxIds = new Set(emails.map((item) => item.candidate_id));
  const visibleEmails = emails.filter((item) => !(["paired_owned_transfer", "user_confirmed_own_transfer"].includes(item.resolution_reason) &&
    item.related_candidate_id && item.candidate_id > item.related_candidate_id &&
    inboxIds.has(item.related_candidate_id)));

  return <section className="mobile-page gmail-automation-page">
    <div className="mobile-page-heading">
      <p className="eyebrow">{tx("Automatización VIP", "VIP automation")}</p>
      <h1>{tx("Movimientos desde Gmail", "Transactions from Gmail")}</h1>
      <span>{tx("DINCR revisa los correos financieros de cada Gmail que autoricés.", "DINCR reviews financial messages in each Gmail account you authorize.")}</span>
    </div>
    <article className={`gmail-connection-card ${gmail?.needs_reauthorization ? "needs-attention" : ""}`}>
      <div className="gmail-connection-heading"><span><Mail size={21}/></span><div><strong>{tx("Tus correos bancarios", "Your banking emails")}</strong><small>{tx("Permiso individual · solo lectura", "Individual permission · read only")}</small></div></div>
      <div className="gmail-privacy-note"><ShieldCheck size={19}/><p>{tx("Podés conectar varios Gmail que controlés. DINCR no puede enviar, modificar ni borrar correos.", "You can connect multiple Gmail accounts you control. DINCR cannot send, edit or delete emails.")}</p></div>
      {!gmail?.connected && <p>{tx("DINCR revisará el historial financiero de los Gmail que autoricés para detectar cuentas y movimientos. Cada hallazgo requiere tu revisión antes de guardarse.", "DINCR will review financial history in the Gmail accounts you authorize to detect accounts and transactions. You review findings before saving them.")}</p>}
      {gmail?.connections?.filter((item) => item.status !== "disabled").map((item) => <div className="gmail-connected-item" key={item.id}>
        <div className="gmail-connection-status"><CheckCircle2 size={18}/><span><strong>{item.google_email}</strong><small>{item.status === "reauthorization_required" ? tx("Necesita reconexión", "Reconnect required") : item.automatic_updates ? tx("Lectura automática activa", "Automatic reading active") : tx("Correo conectado", "Email connected")}</small></span></div>
        <div className="gmail-connection-actions"><button type="button" className="danger" disabled={Boolean(busy)} onClick={() => disconnect(item.id)}><Unplug size={16}/>{tx("Desconectar", "Disconnect")}</button></div>
      </div>)}
        <div className="gmail-privacy-note"><ShieldCheck size={19}/><p>{tx("El acceso es solo lectura. El detalle técnico usado para revisar un hallazgo se elimina después de 30 días y los datos identificativos del correo después de 90 días, cuando no haya revisiones pendientes. El movimiento financiero confirmado se conserva hasta que eliminés tu cuenta. Podés desconectar Gmail cuando querás.", "Access is read-only. Technical evidence used to review a finding is removed after 30 days and identifying email metadata after 90 days when no review is pending. Confirmed financial history is retained until you delete your account. You can disconnect Gmail at any time.")}</p></div>
        <p className="gmail-legal-links"><a href="/terms" target="_blank" rel="noreferrer">{tx("Términos", "Terms")}</a> · <a href="/privacy" target="_blank" rel="noreferrer">{tx("Privacidad", "Privacy")}</a></p>
        {gmail?.consent?.required && <label className="gmail-consent-check"><input type="checkbox" checked={consentAccepted} onChange={(event) => { setConsentAccepted(event.target.checked); setError(""); }}/><span>{tx("Entiendo y acepto que DINCR analice los correos financieros de la cuenta que autorice bajo estas condiciones.", "I understand and agree that DINCR may analyze financial emails from the account I authorize under these conditions.")}</span></label>}
        <button type="button" className="finva-button finva-button-primary" disabled={Boolean(busy) || Boolean(gmail?.consent?.required && !consentAccepted)} onClick={connect}>{busy === "connect" ? tx("Abriendo Google…", "Opening Google…") : gmail?.connected ? tx("Conectar otro Gmail", "Connect another Gmail") : tx("Aceptar y conectar Gmail", "Accept and connect Gmail")}</button>
      {gmail?.connected && <>
        {gmail.pending > 0 && <p>{gmail.pending} {tx("movimiento(s) necesitan revisión.", "transaction(s) need review.")}</p>}
        <div className="gmail-connection-actions"><button type="button" disabled={Boolean(busy)} onClick={sync}><RefreshCw size={16}/>{busy === "sync" ? tx("Actualizando…", "Refreshing…") : tx("Actualizar todos", "Refresh all")}</button></div>
      </>}
    </article>
    {gmail?.connected && identity.items.length > 0 && <section className="gmail-identity" aria-label={tx("Cuentas detectadas", "Detected accounts")}>
      <header><div><p className="eyebrow">{tx("Tu mapa financiero", "Your financial map")}</p><h2>{tx("Cuentas detectadas", "Detected accounts")}</h2></div><span>{identity.summary?.pending || 0} {tx("pendientes", "pending")}</span></header>
      <p>{tx("Confirmá cuáles cuentas son tuyas. DINCR no incluirá una cuenta detectada en tu patrimonio sin tu confirmación.", "Confirm which accounts are yours. DINCR won’t include a detected account in your net worth without your confirmation.")}</p>
      <div className="gmail-identity-list">{identity.items.map((item) => <article key={item.id}>
        <span className="gmail-identity-icon"><Building2 size={19}/></span>
        <div><strong>{item.account_name}</strong><small>{item.bank_name} · {item.institution_country} · {item.currency}</small></div>
        {item.ownership_status === "pending" ? <div className="gmail-account-actions"><button type="button" disabled={Boolean(busy)} onClick={() => confirmAccount(item, "not_mine")}>{tx("No es mía", "Not mine")}</button><button type="button" className="primary" disabled={Boolean(busy)} onClick={() => confirmAccount(item, "own")}>{tx("Es mía", "It’s mine")}</button></div> : <span className={`gmail-ownership-state ${item.ownership_status}`}>{item.ownership_status === "own" ? tx("Cuenta propia", "Owned account") : tx("Cuenta ajena", "Not owned")}</span>}
      </article>)}</div>
    </section>}
    {gmail?.connected && <section className="gmail-inbox" aria-label={tx("Correos financieros", "Financial emails")}>
      <header><div><p className="eyebrow">{tx("Bandeja financiera", "Financial inbox")}</p><h2>{tx("Movimientos detectados", "Detected transactions")}</h2></div><span>{visibleEmails.length}</span></header>
      <div className="gmail-inbox-tabs">
        <button type="button" className={filter === "pending" ? "active" : ""} onClick={() => setFilter("pending")}>{tx("Por revisar", "To review")}</button>
        <button type="button" className={filter === "" ? "active" : ""} onClick={() => setFilter("")}>{tx("Todos", "All")}</button>
      </div>
      {!visibleEmails.length && <div className="gmail-inbox-empty"><Mail size={25}/><strong>{filter ? tx("No hay correos por revisar", "No emails to review") : tx("Todavía no hay correos financieros", "No financial emails yet")}</strong><small>{tx("Cuando DINCR detecte un movimiento bancario aparecerá acá.", "When DINCR detects a bank transaction, it will appear here.")}</small></div>}
      <div className="gmail-email-list">{visibleEmails.map((item) => {
        const pending = item.review_status === "pending";
        const edit = editing?.candidate_id === item.candidate_id;
        const possibleTransfers = transferSuggestions.filter(({ first, second }) =>
          first.candidate_id === item.candidate_id || second.candidate_id === item.candidate_id);
        return <article className="gmail-email-card" key={item.candidate_id || item.email_id}>
          <div className="gmail-email-meta"><span>{item.bank || tx("Banco", "Bank")}</span><time>{item.received_at ? new Date(item.received_at).toLocaleDateString() : ""}</time></div>
          <strong>{item.subject || item.description || tx("Movimiento bancario", "Bank transaction")}</strong>
          <small>{item.sender}</small>
          {item.source_type === "statement" && <p className="gmail-resolution-note">{tx("Detectado en un estado de cuenta PDF. Revisalo igual que cualquier otro movimiento antes de guardarlo.", "Detected in a PDF statement. Review it like any other movement before saving it.")}</p>}
          {item.resolution_reason === "possible_cross_source_match" && <p className="gmail-resolution-note">{tx("Posible coincidencia con una notificación bancaria anterior. DINCR la deja para tu revisión en vez de eliminarla automáticamente.", "Possible match with an earlier bank notification. DINCR leaves it for your review instead of deleting it automatically.")}</p>}
          {item.candidate_id ? edit ? <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); review(item, "accept", { transaction_date: form.get("transaction_date"), description: form.get("description"), amount: Number(form.get("amount")), transaction_type: form.get("transaction_type"), category: form.get("category") }); }} className="gmail-candidate-editor">
            <input name="description" defaultValue={item.description} required aria-label={tx("Descripción", "Description")}/>
            <div><input name="amount" type="number" step="0.01" min="0.01" defaultValue={item.amount} required aria-label={tx("Monto", "Amount")}/><input name="transaction_date" type="date" defaultValue={item.transaction_date} required aria-label={tx("Fecha", "Date")}/></div>
            <div><select name="transaction_type" defaultValue={item.transaction_type}><option value="expense">{tx("Gasto", "Expense")}</option><option value="income">{tx("Ingreso", "Income")}</option><option value="debt_payment">{tx("Pago de deuda", "Debt payment")}</option></select><input name="category" defaultValue={item.category || "general"} required aria-label={tx("Categoría", "Category")}/></div>
            <div className="gmail-review-actions"><button type="button" onClick={() => setEditing(null)}><X size={16}/>{tx("Cancelar", "Cancel")}</button><button className="primary" disabled={Boolean(busy)}><Check size={16}/>{tx("Guardar", "Save")}</button></div>
          </form> : <>
            <div className="gmail-candidate-summary"><span><small>{tx("Descripción", "Description")}</small><b>{item.description}</b></span><span><small>{tx("Monto", "Amount")}</small><b>₡{Number(item.amount || 0).toLocaleString()}</b></span></div>
            {item.is_internal_transfer && <p className="gmail-resolution-note">{item.resolution_reason === "paired_owned_transfer" ? tx("Dos avisos corresponden a un traslado entre tus cuentas confirmadas. Al confirmar, ambos quedan revisados sin sumarse a ingresos o gastos.", "Two notices describe a transfer between your confirmed accounts. Confirming reviews both without adding income or expense.") : tx("DINCR encontró ambas cuentas entre las que confirmaste como propias. Al aceptar, no se registrará como gasto ni ingreso.", "DINCR matched both endpoints to accounts you confirmed as yours. Accepting won’t record income or expense.")}</p>}
            {item.review_status === "duplicate" && <p className="gmail-resolution-note">{tx("DINCR detectó que este correo representa el mismo movimiento que otro registro y evitó contarlo dos veces.", "DINCR detected that this email represents the same movement as another record and avoided double counting it.")}</p>}
            {possibleTransfers.length > 0 && <div className="gmail-transfer-review">
              <strong>{tx("¿Es un traslado entre tus cuentas?", "Is this a transfer between your accounts?")}</strong>
              <small>{tx("DINCR encontró avisos con el mismo monto y fecha. Cada banco puede usar una referencia distinta; verificá que el débito y el crédito sean del mismo traslado.", "DINCR found notices with the same amount and date. Banks may use different references; check that the debit and credit describe the same transfer.")}</small>
              {possibleTransfers.slice(0, 4).map(({ first, second }) => {
                const other = first.candidate_id === item.candidate_id ? second : first;
                const otherVisible = visibleEmails.some((row) => row.candidate_id === other.candidate_id);
                if (otherVisible && item.candidate_id < other.candidate_id) return null;
                const selected = transferReview?.firstId === item.candidate_id && transferReview?.secondId === other.candidate_id;
                return <div key={other.candidate_id}>
                  <button type="button" disabled={Boolean(busy)} onClick={() => setTransferReview({
                    firstId: item.candidate_id, secondId: other.candidate_id,
                    needsDirection: first.direction === "unknown" || second.direction === "unknown",
                    unknownDirection: "", confirmed: false,
                  })}>{tx(`Comparar con ${other.bank} · ${other.date} · ${other.direction === "in" ? "crédito" : other.direction === "out" ? "débito" : "dirección por confirmar"}${other.reference_end ? ` · ref. …${other.reference_end}` : ""}`, `Compare with ${other.bank} · ${other.date} · ${other.direction === "in" ? "credit" : other.direction === "out" ? "debit" : "direction to confirm"}${other.reference_end ? ` · ref. …${other.reference_end}` : ""}`)}</button>
                  {selected && <div className="gmail-transfer-confirm">
                    <p>{tx("Confirmá únicamente si ambas cuentas son tuyas y estos dos avisos corresponden al mismo traslado. Si ya guardaste uno, dejará de contar como ingreso o gasto.", "Confirm only if you own both accounts and these two notices describe one transfer. Previously saved movements will stop counting as income or expense.")}</p>
                    {transferReview.needsDirection && <label>{tx("El aviso sin dirección fue un", "The notice without direction was a")}
                      <select value={transferReview.unknownDirection} onChange={(event) => setTransferReview((current) => ({ ...current, unknownDirection: event.target.value }))}>
                        <option value="">{tx("Seleccioná crédito o débito", "Choose credit or debit")}</option>
                        <option value="in">{tx("Crédito (entró dinero)", "Credit (money came in)")}</option>
                        <option value="out">{tx("Débito (salió dinero)", "Debit (money went out)")}</option>
                      </select>
                    </label>}
                    <label><input type="checkbox" checked={transferReview.confirmed} onChange={(event) => setTransferReview((current) => ({ ...current, confirmed: event.target.checked }))}/>{tx("Confirmo que son mis cuentas y la misma transferencia.", "I confirm that I own both accounts and this is the same transfer.")}</label>
                    <div className="gmail-review-actions"><button type="button" onClick={() => setTransferReview(null)}>{tx("Cancelar", "Cancel")}</button><button type="button" className="primary" disabled={Boolean(busy) || !transferReview.confirmed || (transferReview.needsDirection && !transferReview.unknownDirection)} onClick={confirmTransfer}>{tx("Confirmar traslado propio", "Confirm own transfer")}</button></div>
                  </div>}
                </div>;
              })}
            </div>}
            {pending ? <div className="gmail-review-actions"><button type="button" className="reject" disabled={Boolean(busy)} onClick={() => review(item, "reject")}><X size={16}/>{tx("Rechazar", "Reject")}</button>{!item.is_internal_transfer && <button type="button" disabled={Boolean(busy)} onClick={() => setEditing(item)}><Pencil size={16}/>{tx("Corregir", "Edit")}</button>}<button type="button" className="primary" disabled={Boolean(busy)} onClick={() => review(item, "accept")}><Check size={16}/>{item.is_internal_transfer ? tx("Confirmar transferencia", "Confirm transfer") : tx("Aceptar", "Accept")}</button></div> : <span className={`gmail-review-state ${item.review_status}`}>{item.review_status === "confirmed" || item.review_status === "auto_saved" ? tx("Guardado", "Saved") : item.review_status === "rejected" ? tx("Rechazado", "Rejected") : item.review_status === "duplicate" ? tx("Duplicado", "Duplicate") : item.review_status}</span>}
          </> : <p>{item.parse_reason || tx("DINCR no detectó un movimiento en este correo.", "DINCR did not detect a transaction in this email.")}</p>}
        </article>;
      })}</div>
    </section>}
    {message && <p className="success-banner">{message}</p>}
    {error && <p className="onboarding-error">{error}</p>}
  </section>;
}
