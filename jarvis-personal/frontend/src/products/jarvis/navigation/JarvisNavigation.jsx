import { useState } from "react";
import {
  Activity, Bot, Brain, BriefcaseBusiness, CalendarDays, ChartNoAxesCombined,
  CheckCircle2, CreditCard, Gem, HandCoins, Landmark, ListChecks, LogOut,
  MailSearch, MoreHorizontal, ReceiptText, Settings, Target, TrendingUp,
  UserRound, UsersRound, WalletCards,
} from "lucide-react";
import NativeBottomBar from "../../../ui/native/NativeBottomBar";

const wealthKeys = ["wealth", "investments", "businesses", "financialAccounts", "netWorth", "financialTimeline", "reconciliation", "deterioration"];
const moreKeys = ["receivables", "emails", "transactions", "additionalCards", "chats", "goals", "memory", "settings", "profile", "userManagement", "productOperations"];

const groupFor = (page) => {
  if (moreKeys.includes(page)) return "more";
  if (wealthKeys.includes(page)) return "wealth";
  return page;
};

export default function JarvisNavigation({ activePage, onNavigate, userName, profilePreferences, currentUser, onLogout }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const avatarUrl = profilePreferences?.avatar_data_url || currentUser?.avatar_url || currentUser?.user_metadata?.avatar_url || "";
  const owner = currentUser?.role === "owner" || currentUser?.role === "admin";
  const groups = [
    {
      title: "Dinero y control",
      items: [
        ["receivables", "Cobros y cuentas por recibir", HandCoins],
        ["transactions", "Transacciones", ReceiptText],
        ["emails", "Monitor de correos", MailSearch],
        ["additionalCards", "Tarjetas adicionales", CreditCard],
      ],
    },
    {
      title: "Patrimonio",
      items: [
        ["investments", "Inversiones", TrendingUp],
        ["businesses", "Negocios", BriefcaseBusiness],
        ["financialAccounts", "Cuentas financieras", WalletCards],
        ["netWorth", "Patrimonio neto", Gem],
        ["financialTimeline", "Timeline financiero", CalendarDays],
        ["reconciliation", "Conciliación", CheckCircle2],
        ["deterioration", "Deterioro financiero", Activity],
      ],
    },
    {
      title: "JARVIS personal",
      items: [
        ["goals", "Metas", Target],
        ["memory", "Memory Core", Brain],
        ["settings", "Configuración", Settings],
        ["profile", "Perfil y apariencia", UserRound],
      ],
    },
    ...(owner ? [{
      title: "Administración",
      items: [
        ["userManagement", "Administrar usuarios", UsersRound],
        ["productOperations", "Operaciones FINVA", ListChecks],
      ],
    }] : []),
  ];

  const navigate = (key) => {
    if (key === "more") {
      setMoreOpen((open) => !open);
      return;
    }
    onNavigate(key);
    setMoreOpen(false);
  };

  const items = [
    { key: "dashboard", label: "JARVIS", icon: Bot },
    { key: "strategy", label: "Strategy", icon: ChartNoAxesCombined },
    { key: "finance", label: "Finance", icon: Landmark },
    { key: "wealth", label: "Patrimonio", icon: Gem },
    { key: "more", label: "Más", icon: MoreHorizontal, activeKeys: ["more", ...moreKeys] },
  ];

  return (
    <>
      {moreOpen && (
        <div className="native-more-backdrop" onClick={() => setMoreOpen(false)}>
          <section className="native-more-sheet jarvis-more-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="native-sheet-handle" />
            <header className="native-more-profile">
              <span className="native-more-avatar">
                {avatarUrl ? <img src={avatarUrl} alt="Perfil" /> : <span>{(userName || "K").slice(0, 1).toUpperCase()}</span>}
              </span>
              <span><small>JARVIS</small><strong>{profilePreferences?.display_name || userName || "Kenneth"}</strong></span>
            </header>
            <div className="native-sheet-groups">
              {groups.map((group) => (
                <div className="native-sheet-group" key={group.title}>
                  <small>{group.title}</small>
                  {group.items.map(([key, label, Icon]) => (
                    <button type="button" key={key} className={activePage === key ? "active" : ""} onClick={() => navigate(key)}>
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
      <NativeBottomBar items={items} activeKey={moreOpen ? "more" : groupFor(activePage)} onNavigate={navigate} className="jarvis-native-nav" />
    </>
  );
}
