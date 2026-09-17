import { Laptop, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { applyColorMode, COLOR_MODE_STORAGE_KEY, getSavedColorMode } from "../lib/colorMode";

const OPTIONS = [
  { id: "dark", label: "Oscuro", icon: Moon },
  { id: "light", label: "Claro", icon: Sun },
  { id: "system", label: "Automático", icon: Laptop },
];

export default function AppearanceSelector({ compact = false }) {
  const [mode, setMode] = useState(getSavedColorMode);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const sync = () => applyColorMode(mode);
    sync();
    media.addEventListener?.("change", sync);
    return () => media.removeEventListener?.("change", sync);
  }, [mode]);

  const choose = (nextMode) => {
    localStorage.setItem(COLOR_MODE_STORAGE_KEY, nextMode);
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
