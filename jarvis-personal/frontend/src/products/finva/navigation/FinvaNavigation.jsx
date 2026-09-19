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
  Sparkles,
  Target,
  WalletCards,
} from "lucide-react";
import { useState } from "react";
import NativeBottomBar from "../../../ui/native/NativeBottomBar";
import { deviceLanguage } from "../../../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const primaryItems = [
  { key: "overview", label: tx("Inicio", "Home"), icon: BarChart3 },
  { key: "finance", label: tx("Movimientos", "Transactions"), icon: WalletCards },
  { key: "debts", label: tx("Deudas", "Debts"), icon: CreditCard },
  { key: "goals", label: tx("Metas", "Goals"), icon: Target },
];

export default function FinvaNavigation({ page, plan, onNavigate, onLogout }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const groups = [
    {
      title: tx("Mi dinero", "My money"),
      items: [
        ["situation", tx("Mi situación financiera", "My financial situation"), Landmark],
        ["transactions", tx("Historial completo", "Full history"), ReceiptText],
        ["monthly", tx("Resumen mensual", "Monthly summary"), BarChart3],
      ],
    },
    ...(plan === "free" ? [] : [{
      title: tx("Planificación", "Planning"),
      items: [
        ["strategy", plan === "vip" ? tx("Dirección VIP", "VIP Direction") : tx("Estrategia", "Strategy"), Sparkles],
        ["budget", tx("Presupuesto", "Budget"), WalletCards],
        ["calendar", tx("Calendario", "Calendar"), CalendarDays],
        ["recurring", tx("Pagos recurrentes", "Recurring payments"), Repeat2],
        ["reports", tx("Reportes", "Reports"), BarChart3],
      ],
    }]),
    ...(plan === "vip" ? [{
      title: tx("Inteligencia VIP", "VIP Intelligence"),
      items: [
        ["vip-projections", tx("Proyecciones", "Projections"), TrendingUp],
        ["vip-scenarios", tx("Escenarios", "Scenarios"), Sparkles],
        ["vip-reality", tx("Plan vs realidad", "Plan vs reality"), BarChart3],
        ["vip-emergency", tx("Fondo de emergencia", "Emergency fund"), ShieldCheck],
        ["vip-preferences", tx("Preferencias estratégicas", "Strategic preferences"), SlidersHorizontal],
      ],
    }, { title: tx("Automatización", "Automation"), items: [["gmail", tx("Movimientos desde Gmail", "Transactions from Gmail"), Mail]] }] : []),
    {
      title: tx("Soporte", "Support"),
      items: [
        ["feedback", tx("Ayuda y sugerencias", "Help & feedback"), LifeBuoy],
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
    { key: "more", label: tx("Más", "More"), icon: MoreHorizontal, activeKeys: moreOpen ? ["more", ...secondaryKeys] : secondaryKeys },
  ];

  return (
    <>
      {moreOpen && (
        <div className="native-more-backdrop" onClick={() => setMoreOpen(false)}>
          <section className="native-more-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="native-sheet-handle" />
            <header><small>FINVA</small><strong>{tx("Explorar", "Explore")}</strong></header>
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
              <button type="button" className="native-sheet-logout" onClick={onLogout}><LogOut size={20} /><strong>{tx("Cerrar sesión", "Log out")}</strong></button>
            </div>
          </section>
        </div>
      )}
      <NativeBottomBar items={items} activeKey={moreOpen ? "more" : page} onNavigate={navigate} className="finva-native-nav" />
    </>
  );
}
