import { Bot, ChartNoAxesCombined, Gem, HandCoins, Landmark, UserRound } from "lucide-react";
import NativeBottomBar from "../../../ui/native/NativeBottomBar";

const groupFor = (page) => {
  if (["emails", "transactions", "additionalCards", "chats", "memory", "settings", "goals", "profile", "userManagement", "productOperations"].includes(page)) return "profile";
  if (["investments", "businesses", "financialAccounts", "netWorth", "financialTimeline", "reconciliation", "deterioration", "wealth"].includes(page)) return "wealth";
  return page;
};

export default function JarvisNavigation({ activePage, onNavigate, userName, profilePreferences, currentUser }) {
  const avatarUrl = profilePreferences?.avatar_data_url || currentUser?.avatar_url || currentUser?.user_metadata?.avatar_url || "";
  const items = [
    { key: "dashboard", label: "JARVIS", icon: Bot },
    { key: "strategy", label: "Strategy", icon: ChartNoAxesCombined },
    { key: "finance", label: "Finance", icon: Landmark },
    { key: "receivables", label: "Cobros", icon: HandCoins },
    { key: "wealth", label: "Patrimonio", icon: Gem },
    {
      key: "profile",
      label: "Más",
      icon: UserRound,
      renderIcon: () => (
        <span className="native-nav-avatar">
          {avatarUrl ? <img src={avatarUrl} alt="Perfil" /> : <span>{(userName || "K").slice(0, 1).toUpperCase()}</span>}
        </span>
      ),
    },
  ];

  return <NativeBottomBar items={items} activeKey={groupFor(activePage)} onNavigate={onNavigate} className="jarvis-native-nav" />;
}
