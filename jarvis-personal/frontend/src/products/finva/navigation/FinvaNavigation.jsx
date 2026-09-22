import { BarChart3, CircleUserRound, Sparkles, Target, WalletCards } from "lucide-react";
import NativeBottomBar from "../../../ui/native/NativeBottomBar";
import { deviceLanguage } from "../../../lib/locale";
import { featureEnabled } from "../../../lib/featureFlags";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const primaryItems = [
  { key: "overview", label: tx("Hoy", "Today"), icon: BarChart3 },
  { key: "finance", label: tx("Movimientos", "Transactions"), icon: WalletCards, activeKeys: ["finance", "transactions", "monthly"] },
  { key: "plan", label: tx("Plan", "Plan"), icon: Target, activeKeys: ["plan", "debts", "goals", "savings", "budget", "calendar", "recurring", "vip-emergency", "vip-aguinaldo"] },
  { key: "advisor", label: "DINCR", icon: Sparkles, activeKeys: ["advisor", "strategy", "vip-today", "vip-recommendation", "vip-projections", "vip-projection-detail", "vip-scenarios", "vip-reality", "vip-monthly-review", "vip-preferences", "reports"] },
  { key: "profile", label: tx("Perfil", "Profile"), icon: CircleUserRound, activeKeys: ["profile", "situation", "gmail", "settings", "plan-settings", "feedback"] },
];

export default function FinvaNavigation({ page, plan, onNavigate, featureFlags }) {
  const vipAvailable = featureEnabled(featureFlags, "vip_intelligence");
  const items = primaryItems.map((entry) => entry.key === "advisor" && plan === "vip" && !vipAvailable ? { ...entry, badge: "!" } : entry);
  return <NativeBottomBar items={items} activeKey={page} onNavigate={onNavigate} className="finva-native-nav" />;
}
