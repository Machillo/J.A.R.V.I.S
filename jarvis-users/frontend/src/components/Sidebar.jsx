import { BarChart3, CreditCard, Landmark, LogOut, MoreHorizontal, ReceiptText, Settings, Sparkles, Target, WalletCards } from "lucide-react";
import { useState } from "react";

const mainItems = [
  ["overview", "Resumen", BarChart3],
  ["finance", "Movimientos", WalletCards],
  ["debts", "Deudas", CreditCard],
  ["goals", "Metas", Target],
];

export default function Sidebar({ page, plan, onNavigate, onLogout }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const secondaryItems = [
    ["situation", "Mi situación financiera", Landmark],
    ...(plan === "free" ? [] : [["strategy", plan === "vip" ? "Dirección VIP" : "Estrategia", Sparkles]]),
    ["transactions", "Historial", ReceiptText],
    ["settings", "Cuenta y plan", Settings],
  ];
  const secondaryKeys = secondaryItems.map(([key]) => key);

  const navigate = (key) => {
    onNavigate(key);
    setMoreOpen(false);
  };

  return (
    <>
      {moreOpen && (
        <div className="mobile-more-backdrop" onClick={() => setMoreOpen(false)}>
          <section className="mobile-more-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="sheet-handle" />
            <strong>Más opciones</strong>
            <div className="sheet-actions">
              {secondaryItems.map(([key, label, Icon]) => (
                <button type="button" key={key} className={page === key ? "active" : ""} onClick={() => navigate(key)}>
                  <Icon size={20} />
                  <span>{label}</span>
                </button>
              ))}
              <button type="button" className="sheet-logout" onClick={onLogout}>
                <LogOut size={20} />
                <span>Cerrar sesión</span>
              </button>
            </div>
          </section>
        </div>
      )}

      <nav className="mobile-bottom-nav" aria-label="Navegación principal">
        {mainItems.map(([key, label, Icon]) => (
          <button type="button" key={key} className={page === key ? "active" : ""} onClick={() => navigate(key)}>
            <Icon size={20} />
            <span>{label}</span>
          </button>
        ))}
        <button type="button" className={moreOpen || secondaryKeys.includes(page) ? "active" : ""} onClick={() => setMoreOpen((open) => !open)}>
          <MoreHorizontal size={21} />
          <span>Más</span>
        </button>
      </nav>
    </>
  );
}
