import { AlertTriangle, Banknote, X } from "lucide-react";
import { tx } from "../../lib/locale";
import { useDincrBackHandler } from "../../products/dincr/navigation/useDincrNavigation";

function DialogFrame({ title, description, icon: Icon, tone = "primary", children, onClose, busy }) {
  useDincrBackHandler(() => { if (!busy) onClose(); });
  return (
    <div
      className="dincr-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section className={`dincr-dialog dincr-dialog-${tone}`} role="dialog" aria-modal="true" aria-labelledby="dincr-dialog-title">
        <button className="dincr-dialog-close" type="button" aria-label={tx("Cerrar", "Close")} disabled={busy} onClick={onClose}>
          <X size={20} />
        </button>
        <div className="dincr-dialog-icon"><Icon size={24} /></div>
        <h2 id="dincr-dialog-title">{title}</h2>
        {description && <p>{description}</p>}
        {children}
      </section>
    </div>
  );
}

export function AmountDialog({
  open,
  title,
  description,
  value,
  onValueChange,
  confirmLabel,
  onConfirm,
  onClose,
  busy = false,
  tone = "primary",
}) {
  if (!open) return null;
  const submit = (event) => {
    event.preventDefault();
    if (Number(value) > 0) onConfirm();
  };

  return (
    <DialogFrame title={title} description={description} icon={Banknote} tone={tone} onClose={onClose} busy={busy}>
      <form className="dincr-dialog-form" onSubmit={submit}>
        <label>
          <span>{tx("Monto", "Amount")}</span>
          <div className="dincr-money-input">
            <b>₡</b>
            <input
              autoFocus
              required
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              placeholder="0"
              value={value}
              onChange={(event) => onValueChange(event.target.value)}
            />
          </div>
        </label>
        <div className="dincr-dialog-actions">
          <button className="dincr-button dincr-button-ghost" type="button" disabled={busy} onClick={onClose}>{tx("Cancelar", "Cancel")}</button>
          <button className="dincr-button dincr-button-primary" disabled={busy || Number(value) <= 0}>
            {busy ? tx("Procesando…", "Processing…") : confirmLabel}
          </button>
        </div>
      </form>
    </DialogFrame>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = tx("Eliminar", "Delete"),
  onConfirm,
  onClose,
  busy = false,
  tone = "danger",
}) {
  if (!open) return null;
  return (
    <DialogFrame title={title} description={description} icon={AlertTriangle} tone={tone} onClose={onClose} busy={busy}>
      <div className="dincr-dialog-actions">
        <button className="dincr-button dincr-button-ghost" type="button" disabled={busy} onClick={onClose}>{tx("Cancelar", "Cancel")}</button>
        <button className={`dincr-button dincr-button-${tone}`} type="button" disabled={busy} onClick={onConfirm}>
          {busy ? tx("Procesando…", "Processing…") : confirmLabel}
        </button>
      </div>
    </DialogFrame>
  );
}
