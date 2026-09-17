import { BarChart3, CalendarDays, CreditCard, Landmark, LifeBuoy, LogOut, Mail, MoreHorizontal, ReceiptText, Repeat2, Settings, Sparkles, Target, WalletCards } from "lucide-react";
import { useState } from "react";

const mainItems = [
  ["overview", "Resumen", BarChart3],
  ["finance", "Movimientos", WalletCards],
  ["debts", "Deudas", CreditCard],
  ["goals", "Metas", Target],
];

export default function Sidebar({ page, plan, onNavigate, onLogout }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const secondaryGroups = [
    {
      title: "Mi dinero",
      items: [
        ["situation", "Mi situación financiera", Landmark],
        ["transactions", "Historial completo", ReceiptText],
        ["monthly", "Resumen mensual", BarChart3],
      ],
    },
    ...(plan === "free" ? [] : [{
      title: "Planificación",
      items: [
        ["strategy", plan === "vip" ? "Dirección VIP" : "Estrategia", Sparkles],
        ["budget", "Presupuesto", WalletCards],
        ["calendar", "Calendario", CalendarDays],
        ["recurring", "Pagos recurrentes", Repeat2],
        ["reports", "Reportes", BarChart3],
      ],
    }]),
    ...(plan === "vip" ? [{ title: "Automatización", items: [["gmail", "Movimientos desde Gmail", Mail]] }] : []),
    {
      title: "Cuenta y soporte",
      items: [
        ["settings", "Cuenta, apariencia y plan", Settings],
        ["feedback", "Ayuda y sugerencias", LifeBuoy],
      ],
    },
  ];
  const secondaryItems = secondaryGroups.flatMap((group) => group.items);
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
            <strong>Explorar FINVA</strong>
            <div className="sheet-actions">
              {secondaryGroups.map((group) => (
                <div className="sheet-action-group" key={group.title}>
                  <small>{group.title}</small>
                  {group.items.map(([key, label, Icon]) => (
                    <button type="button" key={key} className={page === key ? "active" : ""} onClick={() => navigate(key)}>
                      <Icon size={20} />
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
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
