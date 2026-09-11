import { AlertTriangle, Banknote, X } from "lucide-react";

function DialogFrame({ title, description, icon: Icon, tone = "primary", children, onClose, busy }) {
  return (
    <div
      className="finva-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section className={`finva-dialog finva-dialog-${tone}`} role="dialog" aria-modal="true" aria-labelledby="finva-dialog-title">
        <button className="finva-dialog-close" type="button" aria-label="Cerrar" disabled={busy} onClick={onClose}>
          <X size={20} />
        </button>
        <div className="finva-dialog-icon"><Icon size={24} /></div>
        <h2 id="finva-dialog-title">{title}</h2>
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
      <form className="finva-dialog-form" onSubmit={submit}>
        <label>
          <span>Monto</span>
          <div className="finva-money-input">
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
        <div className="finva-dialog-actions">
          <button className="finva-button finva-button-ghost" type="button" disabled={busy} onClick={onClose}>Cancelar</button>
          <button className="finva-button finva-button-primary" disabled={busy || Number(value) <= 0}>
            {busy ? "Procesando…" : confirmLabel}
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
  confirmLabel = "Eliminar",
  onConfirm,
  onClose,
  busy = false,
  tone = "danger",
}) {
  if (!open) return null;
  return (
    <DialogFrame title={title} description={description} icon={AlertTriangle} tone={tone} onClose={onClose} busy={busy}>
      <div className="finva-dialog-actions">
        <button className="finva-button finva-button-ghost" type="button" disabled={busy} onClick={onClose}>Cancelar</button>
        <button className={`finva-button finva-button-${tone}`} type="button" disabled={busy} onClick={onConfirm}>
          {busy ? "Procesando…" : confirmLabel}
        </button>
      </div>
    </DialogFrame>
  );
}
