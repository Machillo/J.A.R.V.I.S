import { useState } from "react";
import { LogOut, Trash2, X } from "lucide-react";
import { tx } from "../../../lib/locale";
import { deleteMyAccount } from "../../../users/services/jarvisApi";

export default function AccountActions({ onLogout, variant = "free" }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const removeAccount = async () => {
    setDeleting(true);
    setError("");
    try {
      await deleteMyAccount();
      await onLogout?.();
    } catch (requestError) {
      setError(requestError?.message || tx("No pudimos eliminar tu cuenta. Intentá nuevamente.", "We couldn't delete your account. Please try again."));
      setDeleting(false);
    }
  };

  return <section className={`finva-account-actions finva-account-actions--${variant}`}>
    <div className="finva-account-actions__heading">
      <small>{tx("CUENTA", "ACCOUNT")}</small>
      <strong>{tx("Tu acceso a FINVA", "Your FINVA access")}</strong>
    </div>
    <button className="finva-account-actions__row" type="button" onClick={onLogout}>
      <span><LogOut size={19}/><span><strong>{tx("Cerrar sesión", "Log out")}</strong><small>{tx("Salir de este dispositivo", "Sign out on this device")}</small></span></span>
    </button>
    <button className="finva-account-actions__row finva-account-actions__row--danger" type="button" onClick={() => { setError(""); setConfirming(true); }}>
      <span><Trash2 size={19}/><span><strong>{tx("Eliminar cuenta", "Delete account")}</strong><small>{tx("Borrar permanentemente tu cuenta y tus datos", "Permanently erase your account and data")}</small></span></span>
    </button>

    {confirming && <div className="finva-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="finva-delete-title">
      <button className="finva-delete-dialog__backdrop" type="button" aria-label={tx("Cancelar", "Cancel")} onClick={() => !deleting && setConfirming(false)}/>
      <article>
        <button className="finva-delete-dialog__close" type="button" aria-label={tx("Cerrar", "Close")} onClick={() => setConfirming(false)} disabled={deleting}><X size={20}/></button>
        <span className="finva-delete-dialog__icon"><Trash2 size={24}/></span>
        <h2 id="finva-delete-title">{tx("¿Eliminar tu cuenta?", "Delete your account?")}</h2>
        <p>{tx("Se borrarán permanentemente tu perfil, movimientos, deudas, metas y configuraciones. Esta acción no se puede deshacer.", "Your profile, transactions, debts, goals, and settings will be permanently erased. This action cannot be undone.")}</p>
        {error && <p className="finva-delete-dialog__error" role="alert">{error}</p>}
        <div>
          <button type="button" onClick={() => setConfirming(false)} disabled={deleting}>{tx("Conservar cuenta", "Keep account")}</button>
          <button className="danger" type="button" onClick={removeAccount} disabled={deleting}>{deleting ? tx("Eliminando…", "Deleting…") : tx("Sí, eliminar cuenta", "Yes, delete account")}</button>
        </div>
      </article>
    </div>}
  </section>;
}
