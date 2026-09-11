import { X } from "lucide-react";

export default function FinvaFormSheet({ open, eyebrow = "Nuevo", title, onClose, children }) {
  if (!open) return null;

  return (
    <div
      className="finva-form-sheet-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="finva-form-sheet" role="dialog" aria-modal="true" aria-labelledby="finva-form-sheet-title">
        <header className="finva-form-sheet-header">
          <div>
            <small>{eyebrow}</small>
            <h2 id="finva-form-sheet-title">{title}</h2>
          </div>
          <button className="finva-form-sheet-close" type="button" aria-label="Cerrar" onClick={onClose}>
            <X size={21}/>
          </button>
        </header>
        <div className="finva-form-sheet-body">{children}</div>
      </section>
    </div>
  );
}
