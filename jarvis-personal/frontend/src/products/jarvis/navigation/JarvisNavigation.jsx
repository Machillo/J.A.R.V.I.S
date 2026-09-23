import {
  Bot, ChartNoAxesCombined, Gem, Landmark, WalletCards,
} from "lucide-react";
import NativeBottomBar from "../../../ui/native/NativeBottomBar";
import { deviceLanguage, t } from "../../../lib/locale";

const wealthKeys = ["wealth", "investments", "businesses", "netWorth", "financialTimeline", "reconciliation", "deterioration"];
const profileKeys = ["receivables", "emails", "transactions", "additionalCards", "chats", "moneyControl", "goals", "memory", "settings", "profile", "userManagement", "productOperations"];

const groupFor = (page) => {
  if (profileKeys.includes(page)) return "profile";
  if (wealthKeys.includes(page)) return "wealth";
  return page;
};

export default function JarvisNavigation({ activePage, onNavigate }) {
  const language = deviceLanguage();
  const tr = (key) => t(`nav.${key}`, language);
  const items = [
    { key: "dashboard", label: "Owner", icon: Bot },
    { key: "strategy", label: tr("strategy"), icon: ChartNoAxesCombined },
    { key: "finance", label: tr("finance"), icon: Landmark },
    { key: "financialAccounts", label: tr("accounts"), icon: WalletCards },
    { key: "wealth", label: "Patrim.", icon: Gem, activeKeys: ["wealth", ...wealthKeys] },
  ];

  return <NativeBottomBar items={items} activeKey={groupFor(activePage)} onNavigate={onNavigate} className="jarvis-native-nav" />;
}
