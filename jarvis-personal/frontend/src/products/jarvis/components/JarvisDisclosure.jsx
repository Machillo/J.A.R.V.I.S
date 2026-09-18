import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";

export default function JarvisDisclosure({
  title,
  eyebrow,
  summary,
  icon: Icon,
  actions,
  children,
  defaultOpen = true,
  className = "",
}) {
  const [open, setOpen] = useState(defaultOpen);
  const regionId = useId();

  return (
    <section className={`jarvis-disclosure ${open ? "is-open" : "is-closed"} ${className}`.trim()}>
      <header className="jarvis-disclosure__header">
        <button
          type="button"
          className="jarvis-disclosure__toggle"
          aria-expanded={open}
          aria-controls={regionId}
          onClick={() => setOpen((value) => !value)}
        >
          {Icon ? <span className="jarvis-disclosure__icon"><Icon size={20} /></span> : null}
          <span className="jarvis-disclosure__copy">
            {eyebrow ? <small>{eyebrow}</small> : null}
            <strong>{title}</strong>
            {summary ? <span>{summary}</span> : null}
          </span>
          <ChevronDown className="jarvis-disclosure__chevron" size={20} />
        </button>
        {actions ? <div className="jarvis-disclosure__actions">{actions}</div> : null}
      </header>
      <div id={regionId} className="jarvis-disclosure__region" inert={!open ? "" : undefined}>
        <div className="jarvis-disclosure__body">{children}</div>
      </div>
    </section>
  );
}
