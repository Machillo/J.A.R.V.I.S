import { Laptop, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { applyColorMode, COLOR_MODE_STORAGE_KEY, getSavedColorMode } from "../lib/colorMode";
import { tx } from "../lib/locale";

const OPTIONS = [
  { id: "dark", label: tx("Oscuro", "Dark"), icon: Moon },
  { id: "light", label: tx("Claro", "Light"), icon: Sun },
  { id: "system", label: tx("Automático", "Automatic"), icon: Laptop },
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
        <strong id="appearance-title">{tx("Apariencia", "Appearance")}</strong>
        {!compact && <small>{tx("Elegí un tema o dejá que la app use el del celular.", "Choose a theme or let the app follow your device.")}</small>}
      </div>
      <div className="appearance-options" role="group" aria-label={tx("Tema de la aplicación", "App theme")}>
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
