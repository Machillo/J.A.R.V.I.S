import { useState } from "react";
import { Download, LogOut, Trash2, X } from "lucide-react";
import { tx } from "../../../lib/locale";
import { deleteMyAccount, exportMyData } from "../../../users/services/jarvisApi";
import { saveDataExport } from "../../../lib/dataExport";
import { trackEvent } from "../../../lib/telemetry";

export default function AccountActions({ onLogout, variant = "free" }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  const downloadData = async () => {
    setExporting(true);
    setExportError("");
    try {
      await saveDataExport(await exportMyData());
      trackEvent("data_export_completed");
    } catch (requestError) {
      // Closing the share sheet is not an error.
      if (!/cancel/i.test(requestError?.message || "")) setExportError(requestError?.message || tx("No pudimos preparar tus datos. Intentá nuevamente.", "We couldn't prepare your data. Please try again."));
    } finally {
      setExporting(false);
    }
  };

  const removeAccount = async () => {
    trackEvent("account_deletion_started");
    setDeleting(true);
    setError("");
    try {
      await deleteMyAccount();
      await onLogout?.();
    } catch (requestError) {
      trackEvent("account_deletion_failed");
      const reference = requestError?.errorId ? ` (${tx("referencia", "reference")}: ${requestError.errorId})` : "";
      setError(`${requestError?.message || tx("No pudimos eliminar tu cuenta. Intentá nuevamente.", "We couldn't delete your account. Please try again.")}${reference}`);
      setDeleting(false);
    }
  };

  return <section className={`dincr-account-actions dincr-account-actions--${variant}`}>
    <div className="dincr-account-actions__heading">
      <small>{tx("CUENTA", "ACCOUNT")}</small>
      <strong>{tx("Tu acceso a DINCR", "Your DINCR access")}</strong>
    </div>
    <button className="dincr-account-actions__row" type="button" onClick={onLogout}>
      <span><LogOut size={19}/><span><strong>{tx("Cerrar sesión", "Log out")}</strong><small>{tx("Salir de este dispositivo", "Sign out on this device")}</small></span></span>
    </button>
    <button className="dincr-account-actions__row" type="button" onClick={downloadData} disabled={exporting}>
      <span><Download size={19}/><span><strong>{exporting ? tx("Preparando tus datos…", "Preparing your data…") : tx("Descargar mis datos", "Download my data")}</strong><small>{tx("Copia de tu información en formato JSON", "A copy of your information as JSON")}</small></span></span>
    </button>
    {exportError && <p className="dincr-delete-dialog__error" role="alert">{exportError}</p>}
    <button className="dincr-account-actions__row dincr-account-actions__row--danger" type="button" onClick={() => { setError(""); setConfirming(true); }}>
      <span><Trash2 size={19}/><span><strong>{tx("Eliminar cuenta", "Delete account")}</strong><small>{tx("Borrar permanentemente tu cuenta y tus datos", "Permanently erase your account and data")}</small></span></span>
    </button>

    {confirming && <div className="dincr-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="dincr-delete-title">
      <button className="dincr-delete-dialog__backdrop" type="button" aria-label={tx("Cancelar", "Cancel")} onClick={() => !deleting && setConfirming(false)}/>
      <article>
        <button className="dincr-delete-dialog__close" type="button" aria-label={tx("Cerrar", "Close")} onClick={() => setConfirming(false)} disabled={deleting}><X size={20}/></button>
        <span className="dincr-delete-dialog__icon"><Trash2 size={24}/></span>
        <h2 id="dincr-delete-title">{tx("¿Eliminar tu cuenta?", "Delete your account?")}</h2>
        <p>{tx("Se borrarán permanentemente tu perfil, movimientos, deudas, metas y configuraciones, y se revocará el acceso a tu correo conectado. Esta acción no se puede deshacer.", "Your profile, transactions, debts, goals, and settings will be permanently erased, and access to your connected email will be revoked. This action cannot be undone.")}</p>
        {error && <p className="dincr-delete-dialog__error" role="alert">{error}</p>}
        <div>
          <button type="button" onClick={() => setConfirming(false)} disabled={deleting}>{tx("Conservar cuenta", "Keep account")}</button>
          <button className="danger" type="button" onClick={removeAccount} disabled={deleting}>{deleting ? tx("Eliminando…", "Deleting…") : tx("Sí, eliminar cuenta", "Yes, delete account")}</button>
        </div>
      </article>
    </div>}
  </section>;
}
