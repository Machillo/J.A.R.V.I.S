import { useState } from "react";
import {
  Activity, Bot, Brain, BriefcaseBusiness, CalendarDays, ChartNoAxesCombined,
  CheckCircle2, CreditCard, Gem, HandCoins, Landmark, ListChecks, LogOut,
  MailSearch, MoreHorizontal, ReceiptText, Settings, Target, TrendingUp,
  UserRound, UsersRound, WalletCards,
} from "lucide-react";
import NativeBottomBar from "../../../ui/native/NativeBottomBar";
import JarvisDisclosure from "../components/JarvisDisclosure";
import { deviceLanguage, t } from "../../../lib/locale";

const wealthKeys = ["wealth", "investments", "businesses", "netWorth", "financialTimeline", "reconciliation", "deterioration"];
const moreKeys = ["receivables", "emails", "transactions", "additionalCards", "chats", "goals", "memory", "settings", "profile", "userManagement", "productOperations"];

const groupFor = (page) => {
  if (moreKeys.includes(page)) return "more";
  if (wealthKeys.includes(page)) return "wealth";
  return page;
};

export default function JarvisNavigation({ activePage, onNavigate, userName, profilePreferences, currentUser, onLogout }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const language = deviceLanguage();
  const tr = (key) => t(`nav.${key}`, language);
  const avatarUrl = profilePreferences?.avatar_data_url || currentUser?.avatar_url || currentUser?.user_metadata?.avatar_url || "";
  const owner = currentUser?.role === "owner" || currentUser?.role === "admin";
  const groups = [
    {
      title: tr("moneyControl"),
      items: [
        ["receivables", tr("receivables"), HandCoins],
        ["transactions", tr("transactions"), ReceiptText],
        ["emails", tr("emailMonitor"), MailSearch],
        ["additionalCards", tr("additionalCards"), CreditCard],
      ],
    },
    {
      title: tr("wealth"),
      items: [
        ["investments", tr("investments"), TrendingUp],
        ["businesses", tr("businesses"), BriefcaseBusiness],
        ["netWorth", tr("netWorth"), Gem],
        ["financialTimeline", tr("financialTimeline"), CalendarDays],
        ["reconciliation", tr("reconciliation"), CheckCircle2],
        ["deterioration", tr("deterioration"), Activity],
      ],
    },
    {
      title: tr("personal"),
      items: [
        ["goals", tr("goals"), Target],
        ["memory", tr("memory"), Brain],
        ["settings", tr("settings"), Settings],
        ["profile", tr("profile"), UserRound],
      ],
    },
    ...(owner ? [{
      title: tr("administration"),
      items: [
        ["userManagement", tr("manageUsers"), UsersRound],
        ["productOperations", tr("finvaOperations"), ListChecks],
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
    { key: "strategy", label: tr("strategy"), icon: ChartNoAxesCombined },
    { key: "finance", label: tr("finance"), icon: Landmark },
    { key: "financialAccounts", label: tr("accounts"), icon: WalletCards },
    { key: "wealth", label: tr("wealth"), icon: Gem },
    { key: "more", label: tr("more"), icon: MoreHorizontal, activeKeys: ["more", ...moreKeys] },
  ];

  return (
    <>
      {moreOpen && (
        <div className="native-more-backdrop" onClick={() => setMoreOpen(false)}>
          <section className="native-more-sheet jarvis-more-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="native-sheet-handle" />
            <header className="native-more-profile">
              <span className="native-more-avatar">
                {avatarUrl ? <img src={avatarUrl} alt={tr("profileAlt")} /> : <span>{(userName || "K").slice(0, 1).toUpperCase()}</span>}
              </span>
              <span><small>JARVIS</small><strong>{profilePreferences?.display_name || userName || "Kenneth"}</strong></span>
            </header>
            <div className="native-sheet-groups">
              {groups.map((group) => (
                <JarvisDisclosure title={group.title} className="native-sheet-group" key={group.title}>
                  <div className="native-sheet-group__items">
                  {group.items.map(([key, label, Icon]) => (
                    <button type="button" key={key} className={activePage === key ? "active" : ""} onClick={() => navigate(key)}>
                      <span><Icon size={20} /></span><strong>{label}</strong>
                    </button>
                  ))}
                  </div>
                </JarvisDisclosure>
              ))}
              <button type="button" className="native-sheet-logout" onClick={onLogout}><LogOut size={20} /><strong>{tr("logout")}</strong></button>
            </div>
          </section>
        </div>
      )}
      <NativeBottomBar items={items} activeKey={moreOpen ? "more" : groupFor(activePage)} onNavigate={navigate} className="jarvis-native-nav" />
    </>
  );
}
