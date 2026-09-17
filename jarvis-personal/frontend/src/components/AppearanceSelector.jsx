import { Laptop, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

const STORAGE_KEY = "finva-color-mode";
const OPTIONS = [
  { id: "dark", label: "Oscuro", icon: Moon },
  { id: "light", label: "Claro", icon: Sun },
  { id: "system", label: "Automático", icon: Laptop },
];

const resolveMode = (mode) => (
  mode === "system"
    ? (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
    : mode
);

const applyMode = (mode) => {
  document.documentElement.dataset.colorMode = mode;
  document.documentElement.dataset.colorModeResolved = resolveMode(mode);
  document.documentElement.style.colorScheme = resolveMode(mode);
};

export function initializeColorMode() {
  const saved = localStorage.getItem(STORAGE_KEY);
  applyMode(OPTIONS.some(({ id }) => id === saved) ? saved : "system");
}

export default function AppearanceSelector({ compact = false }) {
  const [mode, setMode] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return OPTIONS.some(({ id }) => id === saved) ? saved : "system";
  });

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const sync = () => applyMode(mode);
    sync();
    media.addEventListener?.("change", sync);
    return () => media.removeEventListener?.("change", sync);
  }, [mode]);

  const choose = (nextMode) => {
    localStorage.setItem(STORAGE_KEY, nextMode);
    setMode(nextMode);
  };

  return (
    <section className={`appearance-card ${compact ? "compact" : ""}`} aria-labelledby="appearance-title">
      <div className="appearance-copy">
        <strong id="appearance-title">Apariencia</strong>
        {!compact && <small>Elegí un tema o dejá que la app use el del celular.</small>}
      </div>
      <div className="appearance-options" role="group" aria-label="Tema de la aplicación">
        {OPTIONS.map(({ id, label, icon: Icon }) => (
          <button
            type="button"
            key={id}
            className={mode === id ? "active" : ""}
            aria-pressed={mode === id}
            onClick={() => choose(id)}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
