import {
  BarChart3,
  CalendarDays,
  CreditCard,
  Landmark,
  LifeBuoy,
  LogOut,
  Mail,
  MoreHorizontal,
  ReceiptText,
  Repeat2,
  Settings,
  Sparkles,
  Target,
  WalletCards,
} from "lucide-react";
import { useState } from "react";
import NativeBottomBar from "../../../ui/native/NativeBottomBar";

const primaryItems = [
  { key: "overview", label: "Resumen", icon: BarChart3 },
  { key: "finance", label: "Movimientos", icon: WalletCards },
  { key: "debts", label: "Deudas", icon: CreditCard },
  { key: "goals", label: "Metas", icon: Target },
];

export default function FinvaNavigation({ page, plan, onNavigate, onLogout }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const groups = [
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
  const secondaryKeys = groups.flatMap((group) => group.items.map(([key]) => key));

  const navigate = (key) => {
    if (key === "more") {
      setMoreOpen((open) => !open);
      return;
    }
    onNavigate(key);
    setMoreOpen(false);
  };

  const items = [
    ...primaryItems,
    { key: "more", label: "Más", icon: MoreHorizontal, activeKeys: moreOpen ? ["more", ...secondaryKeys] : secondaryKeys },
  ];

  return (
    <>
      {moreOpen && (
        <div className="native-more-backdrop" onClick={() => setMoreOpen(false)}>
          <section className="native-more-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="native-sheet-handle" />
            <header><small>FINVA</small><strong>Explorar</strong></header>
            <div className="native-sheet-groups">
              {groups.map((group) => (
                <div className="native-sheet-group" key={group.title}>
                  <small>{group.title}</small>
                  {group.items.map(([key, label, Icon]) => (
                    <button type="button" key={key} className={page === key ? "active" : ""} onClick={() => navigate(key)}>
                      <span><Icon size={20} /></span><strong>{label}</strong>
                    </button>
                  ))}
                </div>
              ))}
              <button type="button" className="native-sheet-logout" onClick={onLogout}><LogOut size={20} /><strong>Cerrar sesión</strong></button>
            </div>
          </section>
        </div>
      )}
      <NativeBottomBar items={items} activeKey={moreOpen ? "more" : page} onNavigate={navigate} className="finva-native-nav" />
    </>
  );
}
