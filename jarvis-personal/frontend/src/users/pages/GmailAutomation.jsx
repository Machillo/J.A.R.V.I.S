import { CheckCircle2, Mail, RefreshCw, ShieldCheck, Unplug } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Browser } from "@capacitor/browser";
import { App } from "@capacitor/app";
import {
  connectVipGmail,
  disconnectVipGmail,
  getVipGmailStatus,
  syncVipGmail,
} from "../services/jarvisApi";
import { tx } from "../../lib/locale";

export default function GmailAutomation() {
  const [gmail, setGmail] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try { setGmail(await getVipGmailStatus()); }
    catch (err) { setError(err.message || tx("No se pudo consultar Gmail.", "Couldn’t check Gmail.")); }
  }, []);

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
    {message && <p className="success-banner">{message}</p>}
    {error && <p className="onboarding-error">{error}</p>}
  </section>;
}
