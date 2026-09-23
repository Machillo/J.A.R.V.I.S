import { X } from "lucide-react";
import { tx } from "../../lib/locale";
import { useDincrBackHandler } from "../../products/dincr/navigation/useDincrNavigation";

export default function DincrFormSheet({ open, eyebrow = tx("Nuevo", "New"), title, onClose, children }) {
  useDincrBackHandler(onClose, open);
  if (!open) return null;

  return (
    <div
      className="dincr-form-sheet-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="dincr-form-sheet" role="dialog" aria-modal="true" aria-labelledby="dincr-form-sheet-title">
        <header className="dincr-form-sheet-header">
          <div>
            <small>{eyebrow}</small>
            <h2 id="dincr-form-sheet-title">{title}</h2>
          </div>
          <button className="dincr-form-sheet-close" type="button" aria-label={tx("Cerrar", "Close")} onClick={onClose}>
            <X size={21}/>
          </button>
        </header>
        <div className="dincr-form-sheet-body">{children}</div>
      </section>
    </div>
  );
}
