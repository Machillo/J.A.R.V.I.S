import { Building2, Check, CheckCircle2, Mail, Pencil, RefreshCw, ShieldCheck, Unplug, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Browser } from "@capacitor/browser";
import {
  connectVipGmail,
  connectVipMicrosoftMail,
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
import { categoryLabel, categoryValue } from "../../lib/categories";
import { trackEvent } from "../../lib/telemetry";
import { MAIL_OAUTH_RESULT_EVENT, takeMailOAuthOutcome } from "../../lib/mailOAuth";
import LegalLink from "../../components/LegalLink";
import gmailLogo from "../../assets/institutions/gmail.png";
import outlookLogo from "../../assets/institutions/outlook.svg";

// Codes returned by the backend callback in com.<app>://gmail/callback?<gmail|microsoft>=<code>.
const MAIL_ERRORS = {
  denied: ["No autorizaste el acceso a {provider}. Podés intentarlo de nuevo cuando quieras.", "You didn’t authorize {provider} access. You can try again anytime."],
  invalid_state: ["La autorización venció o ya se usó. Volvé a conectar {provider}.", "The authorization expired or was already used. Connect {provider} again."],
  permission_missing: ["No se concedió el permiso de lectura de correo. Volvé a conectar {provider} y aceptá el acceso de lectura.", "Mail read access wasn’t granted. Connect {provider} again and accept read access."],
  vip_required: ["Conectar {provider} requiere el plan VIP activo.", "Connecting {provider} requires an active VIP plan."],
  already_connected_elsewhere: ["Ese correo ya está conectado de otra forma en DINCR.", "That mailbox is already connected to DINCR another way."],
  mailbox_missing: ["Esa cuenta no tiene un buzón de correo disponible.", "That account has no mailbox available."],
  already_processed: ["Esta autorización de {provider} ya se procesó. Si no aparece conectado, volvé a conectarlo.", "This {provider} authorization was already processed. If it doesn’t show as connected, connect it again."],
  completion_pending: ["No pudimos terminar de conectar {provider} por la conexión. DINCR lo reintentará cuando vuelvas a estar en línea.", "We couldn’t finish connecting {provider} because of the connection. DINCR will retry when you’re back online."],
};

function mailErrorMessage(provider, code) {
  const name = provider === "microsoft" ? "Outlook" : "Gmail";
  const [es, en] = MAIL_ERRORS[code] || ["No pudimos conectar {provider}. Intentalo de nuevo en unos minutos.", "We couldn’t connect {provider}. Please try again in a few minutes."];
  return tx(es, en).replaceAll("{provider}", name);
}

function MailProviderLogo({ provider }) {
  return <img className="mail-provider-logo" src={provider === "microsoft" ? outlookLogo : gmailLogo} alt="" aria-hidden="true" />;
}

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
    catch (err) { setError(err.message || tx("No se pudo consultar el correo.", "Couldn’t check mail.")); }
  }, [filter]);

  const review = async (item, action, corrections = null) => {
    setBusy(`${action}-${item.candidate_id}`); setError(""); setMessage("");
    try {
      if (action === "reject") await rejectVipGmailCandidate(item.candidate_id);
      else await acceptVipGmailCandidate(item.candidate_id, corrections);
      trackEvent("email_candidate_reviewed", {
        decision: action === "reject" ? "rejected" : corrections ? "corrected" : "accepted",
        source_type: "email",
      });
      trackEvent("transaction_candidate_reviewed", { decision: action === "reject" ? "rejected" : corrections ? "corrected" : "accepted", source_type: "email" });
      if (action === "reject") trackEvent("transaction_rejected", { source_type: "email" });
      else if (!item.is_internal_transfer) trackEvent("transaction_confirmed", { source_type: "email" });
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
        ownership_status: ownershipStatus,
      });
      if (ownershipStatus === "own") trackEvent("financial_account_confirmed");
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
    // UsersApp redeems the OAuth return; this screen only reports the outcome.
    const showOutcome = () => {
      const outcome = takeMailOAuthOutcome();
      if (!outcome) return;
      if (outcome.ok) {
        // Gmail is counted server-side as gmail_connected; only other providers report here.
        if (outcome.provider !== "gmail") trackEvent("mail_connected", { source_type: "email" });
        setError("");
        setMessage(tx("Correo conectado. DINCR está revisando tus avisos financieros.", "Mailbox connected. DINCR is reviewing your financial notices."));
      } else {
        setMessage("");
        setError(outcome.code === "completion_failed" && outcome.message ? outcome.message : mailErrorMessage(outcome.provider, outcome.code));
      }
      load();
    };
    showOutcome();
    window.addEventListener(MAIL_OAUTH_RESULT_EVENT, showOutcome);
    return () => {
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener(MAIL_OAUTH_RESULT_EVENT, showOutcome);
    };
  }, [load]);

  const connect = async (provider) => {
    setBusy("connect"); setError(""); setMessage("");
    try {
      if (gmail?.consent?.required) {
        if (!consentAccepted) throw new Error(tx("Debés aceptar la explicación de Email Monitor antes de conectarlo.", "You must accept the Email Monitor explanation before connecting it."));
        await acceptVipGmailConsent(gmail.consent.version);
      }
      const response = await (provider === "microsoft" ? connectVipMicrosoftMail() : connectVipGmail());
      trackEvent("gmail_connection_started", { source_type: "email" });
      if (!response?.authorization_url) throw new Error(tx("El proveedor no devolvió una dirección de autorización.", "The provider did not return an authorization URL."));
      await Browser.open({ url: response.authorization_url, presentationStyle: "popover" });
    } catch (err) { setError(err.message || tx("No se pudo abrir Google.", "Couldn’t open Google.")); }
    finally { setBusy(""); }
  };

  const sync = async () => {
    trackEvent("gmail_sync_started", { source_type: "email" });
    setBusy("sync"); setError(""); setMessage("");
    try {
      const result = await syncVipGmail();
      trackEvent("gmail_sync_completed", {
        scan_scope: result.scan_scope || "unknown",
        initial_scan_complete: Boolean(result.initial_scan_complete),
        success: result.status === "ok",
      });
      await load();
      const progress = result.scan_scope === "year_to_date" && !result.initial_scan_complete
        ? tx(" DINCR continuará recorriendo el resto del año en las próximas actualizaciones.", " DINCR will continue scanning the rest of the year during the next refreshes.")
        : "";
      setMessage(tx(`Listo: ${result.auto_saved || 0} movimientos nuevos y ${result.pending || 0} por revisar.`, `Done: ${result.auto_saved || 0} new transactions and ${result.pending || 0} to review.`) + progress + (result.failed_connections?.length ? tx(" Algunas conexiones necesitan atención.", "Some connections need attention.") : ""));
    } catch (err) {
      trackEvent("gmail_sync_failed", { success: false });
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
      setMessage(tx("Ese correo quedó desconectado de DINCR.", "That mailbox was disconnected from DINCR."));
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
      <h1>{tx("Movimientos desde tu correo", "Transactions from your email")}</h1>
      <span>{tx("DINCR revisa los correos financieros de cada buzón compatible que autoricés.", "DINCR reviews financial messages in each supported mailbox you authorize.")}</span>
    </div>
    <article className={`gmail-connection-card ${gmail?.needs_reauthorization ? "needs-attention" : ""}`}>
      <div className="gmail-connection-heading"><span><Mail size={21}/></span><div><strong>{tx("Tus correos bancarios", "Your banking emails")}</strong><small>{tx("Permiso individual · solo lectura", "Individual permission · read only")}</small></div></div>
      <div className="gmail-privacy-note"><ShieldCheck size={19}/><p>{tx("Podés conectar varios Gmail y Outlook/Hotmail que controlés. DINCR solicita acceso de lectura, sin permiso para enviar, modificar ni borrar correos.", "You can connect multiple Gmail and Outlook/Hotmail accounts you control. DINCR requests read access, without permission to send, edit or delete emails.")}</p></div>
      {!gmail?.connected && <p>{tx("DINCR revisará los avisos financieros de los buzones que autoricés para detectar cuentas y movimientos. Cada hallazgo requiere tu revisión antes de guardarse.", "DINCR will review financial notices in the mailboxes you authorize to detect accounts and transactions. You review findings before saving them.")}</p>}
      {gmail?.connections?.filter((item) => item.status !== "disabled").map((item) => <div className="gmail-connected-item" key={item.id}>
        <div className="gmail-connection-status"><MailProviderLogo provider={item.provider}/><span><strong>{item.google_email}</strong><small>{item.provider === "microsoft" ? "Outlook / Hotmail · " : "Gmail · "}{item.status === "reauthorization_required" ? tx("Necesita reconexión", "Reconnect required") : item.automatic_updates ? tx("Lectura automática activa", "Automatic reading active") : tx("Correo conectado", "Email connected")}</small></span><CheckCircle2 className="mail-provider-status" size={18} aria-hidden="true"/></div>
        <div className="gmail-connection-actions"><button type="button" className="danger" disabled={Boolean(busy)} onClick={() => disconnect(item.id)}><Unplug size={16}/>{tx("Desconectar", "Disconnect")}</button></div>
      </div>)}
        <div className="gmail-privacy-note"><ShieldCheck size={19}/><p>{tx("El acceso es solo lectura. El detalle técnico usado para revisar un hallazgo se elimina después de 30 días y los datos identificativos del correo después de 90 días, cuando no haya revisiones pendientes. El movimiento financiero confirmado se conserva hasta que eliminés tu cuenta. Podés desconectar cada correo cuando querás.", "Access is read-only. Technical evidence used to review a finding is removed after 30 days and identifying email metadata after 90 days when no review is pending. Confirmed financial history is retained until you delete your account. You can disconnect each mailbox at any time.")}</p></div>
        <p className="gmail-legal-links"><LegalLink kind="terms">{tx("Términos", "Terms")}</LegalLink> · <LegalLink kind="privacy">{tx("Privacidad", "Privacy")}</LegalLink></p>
        {gmail?.consent?.required && <label className="gmail-consent-check"><input type="checkbox" checked={consentAccepted} onChange={(event) => { setConsentAccepted(event.target.checked); setError(""); }}/><span>{tx("Entiendo y acepto que DINCR analice los correos financieros de la cuenta que autorice bajo estas condiciones.", "I understand and agree that DINCR may analyze financial emails from the account I authorize under these conditions.")}</span></label>}
        <div className="gmail-provider-actions">
          <button type="button" className="finva-button finva-button-primary" disabled={Boolean(busy) || Boolean(gmail?.consent?.required && !consentAccepted)} onClick={() => connect("gmail")}><MailProviderLogo provider="gmail"/>{busy === "connect" ? tx("Abriendo…", "Opening…") : tx("Conectar Gmail", "Connect Gmail")}</button>
          <button type="button" className="finva-button finva-button-primary" disabled={Boolean(busy) || !gmail?.microsoft_available || Boolean(gmail?.consent?.required && !consentAccepted)} onClick={() => connect("microsoft")}><MailProviderLogo provider="microsoft"/>{gmail?.microsoft_available ? tx("Conectar Outlook / Hotmail", "Connect Outlook / Hotmail") : tx("Outlook / Hotmail: pendiente de configurar", "Outlook / Hotmail: setup pending")}</button>
        </div>
        <p>{tx("Yahoo aún no está disponible: su permiso para leer buzones requiere aprobación de Yahoo. No ingresés tu contraseña de Yahoo en DINCR.", "Yahoo is not available yet: mailbox read access requires Yahoo approval. Do not enter your Yahoo password in DINCR.")}</p>
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
          {item.candidate_id ? edit ? <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); review(item, "accept", { transaction_date: form.get("transaction_date"), description: form.get("description"), amount: Number(form.get("amount")), transaction_type: form.get("transaction_type"), category: categoryValue(form.get("category")) }); }} className="gmail-candidate-editor">
            <input name="description" defaultValue={item.description} required aria-label={tx("Descripción", "Description")}/>
            <div><input name="amount" type="number" step="0.01" min="0.01" defaultValue={item.amount} required aria-label={tx("Monto", "Amount")}/><input name="transaction_date" type="date" defaultValue={item.transaction_date} required aria-label={tx("Fecha", "Date")}/></div>
            <div><select name="transaction_type" defaultValue={item.transaction_type}><option value="expense">{tx("Gasto", "Expense")}</option><option value="income">{tx("Ingreso", "Income")}</option><option value="debt_payment">{tx("Pago de deuda", "Debt payment")}</option></select><input name="category" defaultValue={categoryLabel(item.category || "general")} required aria-label={tx("Categoría", "Category")}/></div>
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
