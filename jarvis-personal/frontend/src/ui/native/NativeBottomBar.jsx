import { deviceLanguage, tx } from "../../lib/locale";

export default function NativeBottomBar({ items, activeKey, onNavigate, className = "" }) {
  const language = deviceLanguage();
  return (
    <nav className={`native-bottom-nav ${className}`.trim()} style={{ "--native-nav-count": items.length }} aria-label={tx("Navegación principal", "Main navigation", language)}>
      {items.map((item) => {
        const Icon = item.icon;
        const active = item.activeKeys?.includes(activeKey) || item.key === activeKey;
        return (
          <button
            type="button"
            key={item.key}
            className={active ? "active" : ""}
            aria-current={active ? "page" : undefined}
            aria-label={item.label}
            onClick={() => onNavigate(item.key)}
          >
            <span className="native-nav-icon">
              {item.renderIcon ? item.renderIcon(active) : <Icon size={23} strokeWidth={active ? 2.35 : 1.85} />}
              {item.badge ? <small>{item.badge}</small> : null}
            </span>
            <span className="native-nav-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
