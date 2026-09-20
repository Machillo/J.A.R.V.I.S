import Budget from "../../../users/pages/Budget";
import FinancialCalendar from "../../../users/pages/Calendar";
import FinvaOverview from "./overview/FinvaOverview";
import Debts from "../../../users/pages/Debts";
import Feedback from "../../../users/pages/Feedback";
import Finance from "../../../users/pages/Finance";
import FinancialSituation from "../../../users/pages/FinancialSituation";
import GmailAutomation from "../../../users/pages/GmailAutomation";
import Goals from "../../../users/pages/Goals";
import MonthlySummary from "../../../users/pages/MonthlySummary";
import Recurring from "../../../users/pages/Recurring";
import Reports from "../../../users/pages/Reports";
import SettingsPage from "../../../users/pages/Settings";
import StrategyBasic from "../../../users/pages/StrategyBasic";
import Transactions from "../../../users/pages/Transactions";
import VipScreens from "./vip/VipScreens";
import { FreeMore, FreeSettings } from "./free/FreeScreens";
import BasicMore from "./basic/BasicScreens";
import { featureEnabled } from "../../../lib/featureFlags";
import FeatureUnavailable from "./FeatureUnavailable";

export function createFinvaFeatureRegistry({ user, plan, navigate, onUserChange, onLogout, featureFlags }) {
  const gated = (flagKey, component) => featureEnabled(featureFlags, flagKey) ? component : <FeatureUnavailable flags={featureFlags} flagKey={flagKey}/>;
  const vipEnabled = featureEnabled(featureFlags, "vip_intelligence");
  return {
    overview: plan === "vip" && vipEnabled ? <VipScreens view="dashboard" user={user} onNavigate={navigate} /> : <FinvaOverview user={user} plan={plan} onNavigate={navigate} />,
    finance: <Finance plan={plan} />,
    debts: <Debts plan={plan} />,
    strategy: plan === "vip" ? gated("vip_intelligence", <VipScreens view="strategy" user={user} onNavigate={navigate} />) : <StrategyBasic plan={plan} />,
    gmail: plan === "vip" ? gated("gmail_automation", <GmailAutomation />) : <SettingsPage user={user} onUserChange={onUserChange} />,
    goals: plan === "vip" ? <VipScreens view="goal" user={user} onNavigate={navigate} /> : <Goals plan={plan} />,
    savings: <Goals plan={plan} initialView="savings" />,
    transactions: <Transactions />,
    situation: <FinancialSituation plan={plan} onNavigate={navigate} />,
    more: plan === "free" ? <FreeMore onNavigate={navigate} onLogout={onLogout} /> : plan === "basic" ? <BasicMore onNavigate={navigate} onLogout={onLogout} /> : <VipScreens view="more" user={user} onNavigate={navigate} onLogout={onLogout} />,
    settings: plan === "free" ? <FreeSettings user={user} onNavigate={navigate} onLogout={onLogout} /> : <SettingsPage user={user} onUserChange={onUserChange} />,
    "plan-settings": <SettingsPage user={user} onUserChange={onUserChange} />,
    budget: <Budget plan={plan} />,
    calendar: <FinancialCalendar plan={plan} />,
    recurring: <Recurring plan={plan} />,
    reports: gated("advanced_reports", <Reports plan={plan} />),
    monthly: <MonthlySummary />,
    feedback: <Feedback />,
    "vip-recommendation": gated("vip_intelligence", <VipScreens view="recommendation" user={user} onNavigate={navigate} />),
    "vip-projections": gated("vip_intelligence", <VipScreens view="projections" user={user} onNavigate={navigate} />),
    "vip-projection-detail": gated("vip_intelligence", <VipScreens view="projection-detail" user={user} onNavigate={navigate} />),
    "vip-scenarios": gated("vip_intelligence", <VipScreens view="scenarios" user={user} onNavigate={navigate} />),
    "vip-reality": gated("vip_intelligence", <VipScreens view="reality" user={user} onNavigate={navigate} />),
    "vip-monthly-review": gated("vip_intelligence", <VipScreens view="monthly-review" user={user} onNavigate={navigate} />),
    "vip-today": gated("vip_intelligence", <VipScreens view="today" user={user} onNavigate={navigate} />),
    "vip-emergency": gated("vip_intelligence", <VipScreens view="emergency" user={user} onNavigate={navigate} />),
    "vip-preferences": gated("vip_intelligence", <VipScreens view="preferences" user={user} onNavigate={navigate} />),
  };
}
