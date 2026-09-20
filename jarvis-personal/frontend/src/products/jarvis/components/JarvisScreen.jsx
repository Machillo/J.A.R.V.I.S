import { ChevronRight } from "lucide-react";

export function JarvisScreen({ eyebrow, title, subtitle, actions, children, className = "" }) {
  return (
    <section className={`jarvis-screen ${className}`.trim()}>
      <header className="jarvis-screen__header">
        <div>
          {eyebrow && <span className="jarvis-screen__eyebrow">{eyebrow}</span>}
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {actions && <div className="jarvis-screen__actions">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

export function JarvisGlassCard({ as: Tag = "article", className = "", children, ...props }) {
  return <Tag className={`jarvis-glass-card ${className}`.trim()} {...props}>{children}</Tag>;
}

export function JarvisMenuRow({ icon: Icon, title, detail, meta, onClick }) {
  return (
    <button type="button" className="jarvis-menu-row" onClick={onClick}>
      <span className="jarvis-menu-row__icon"><Icon size={21} strokeWidth={1.9} /></span>
      <span className="jarvis-menu-row__copy">
        <strong>{title}</strong>
        {detail && <small>{detail}</small>}
      </span>
      {meta && <span className="jarvis-menu-row__meta">{meta}</span>}
      <ChevronRight className="jarvis-menu-row__chevron" size={18} />
    </button>
  );
}

export function JarvisStatusPill({ tone = "info", children }) {
  return <span className={`jarvis-status-pill is-${tone}`}>{children}</span>;
}
