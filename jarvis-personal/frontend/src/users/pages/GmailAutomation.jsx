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

export default function GmailAutomation() {
  const [gmail, setGmail] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try { setGmail(await getVipGmailStatus()); }
    catch (err) { setError(err.message || "No se pudo consultar Gmail."); }
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
      if (!response?.authorization_url) throw new Error("Google no devolvió una dirección de autorización.");
      await Browser.open({ url: response.authorization_url, presentationStyle: "popover" });
    } catch (err) { setError(err.message || "No se pudo abrir Google."); }
    finally { setBusy(""); }
  };

  const sync = async () => {
    setBusy("sync"); setError(""); setMessage("");
    try {
      const result = await syncVipGmail();
      await load();
      setMessage(`Listo: ${result.auto_saved || 0} movimientos nuevos y ${result.pending || 0} por revisar.`);
    } catch (err) { setError(err.message || "No se pudo actualizar Gmail."); }
    finally { setBusy(""); }
  };

  const disconnect = async () => {
    setBusy("disconnect"); setError(""); setMessage("");
    try {
      await disconnectVipGmail();
      setGmail({ connected: false, status: "disconnected" });
      setMessage("Gmail quedó desconectado de FINVA.");
    } catch (err) { setError(err.message || "No se pudo desconectar Gmail."); }
    finally { setBusy(""); }
  };

  return <section className="mobile-page gmail-automation-page">
    <div className="mobile-page-heading">
      <p className="eyebrow">Automatización VIP</p>
      <h1>Movimientos desde Gmail</h1>
      <span>FINVA importa notificaciones bancarias de la cuenta que autoricés.</span>
    </div>
    <article className={`gmail-connection-card ${gmail?.needs_reauthorization ? "needs-attention" : ""}`}>
      <div className="gmail-connection-heading"><span><Mail size={21}/></span><div><strong>Tu correo bancario</strong><small>Permiso individual · solo lectura</small></div></div>
      <div className="gmail-privacy-note"><ShieldCheck size={19}/><p>Cada usuario conecta únicamente su propio Gmail. FINVA no puede enviar, modificar ni borrar correos.</p></div>
      {!gmail?.connected ? <>
        <p>{gmail?.needs_reauthorization ? "El permiso venció o fue revocado. Reconectalo para continuar." : "Conectá el Gmail donde recibís las notificaciones de tus bancos."}</p>
        <button type="button" className="finva-button finva-button-primary" disabled={Boolean(busy)} onClick={connect}>{busy === "connect" ? "Abriendo Google…" : gmail?.needs_reauthorization ? "Reconectar Gmail" : "Conectar mi Gmail"}</button>
      </> : <>
        <div className="gmail-connection-status"><CheckCircle2 size={18}/><span><strong>{gmail.google_email}</strong><small>{gmail.automatic_updates ? "Lectura automática activa" : "Correo conectado"}</small></span></div>
        {gmail.pending > 0 && <p>{gmail.pending} movimiento(s) necesitan revisión.</p>}
        <div className="gmail-connection-actions"><button type="button" disabled={Boolean(busy)} onClick={sync}><RefreshCw size={16}/>{busy === "sync" ? "Actualizando…" : "Actualizar ahora"}</button><button type="button" className="danger" disabled={Boolean(busy)} onClick={disconnect}><Unplug size={16}/>Desconectar</button></div>
      </>}
    </article>
    {message && <p className="success-banner">{message}</p>}
    {error && <p className="onboarding-error">{error}</p>}
  </section>;
}
