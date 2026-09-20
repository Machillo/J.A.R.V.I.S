import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { Download, RefreshCw, ShieldAlert, X } from "lucide-react";
import { tx } from "../lib/locale";

async function openUpdateUrl(url) {
  if (!url) return;
  if (Capacitor.isNativePlatform()) await Browser.open({ url });
  else window.open(url, "_blank", "noopener,noreferrer");
}

export default function ReleaseUpdateNotice({ policy, required = false, onDismiss, onRefresh }) {
  const message = tx(policy?.message_es, policy?.message_en)
    || tx("Hay una nueva versión de FINVA disponible.", "A new FINVA version is available.");

  if (required) {
    return (
      <main className="finva-release-gate" role="alert" aria-live="assertive">
        <section className="finva-release-gate__card">
          <ShieldAlert size={42} aria-hidden="true" />
          <small>FINVA · {policy?.current_version}</small>
          <h1>{tx("Actualización necesaria", "Update required")}</h1>
          <p>{message}</p>
          <span>{tx("Esta versión ya no es compatible. Actualizá para proteger tus datos y continuar.", "This version is no longer compatible. Update to protect your data and continue.")}</span>
          {policy?.update_url ? (
            <button type="button" onClick={() => openUpdateUrl(policy.update_url)}><Download size={19} /> {tx("Actualizar FINVA", "Update FINVA")}</button>
          ) : (
            <button type="button" onClick={onRefresh}><RefreshCw size={19} /> {tx("Comprobar nuevamente", "Check again")}</button>
          )}
        </section>
      </main>
    );
  }

  return (
    <aside className="finva-release-banner" role="status">
      <div><strong>{tx("Nueva versión disponible", "New version available")}</strong><span>{message}</span></div>
      {policy?.update_url && <button type="button" onClick={() => openUpdateUrl(policy.update_url)}><Download size={17} /> {tx("Actualizar", "Update")}</button>}
      <button className="finva-release-banner__close" type="button" aria-label={tx("Cerrar aviso", "Close notice")} onClick={onDismiss}><X size={18} /></button>
    </aside>
  );
}
