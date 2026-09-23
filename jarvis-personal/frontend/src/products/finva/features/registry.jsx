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
import VipStrategy from "../../../users/pages/VipStrategy";
import Transactions from "../../../users/pages/Transactions";
import VipScreens from "./vip/VipScreens";
import { FreeMore, FreeSettings } from "./free/FreeScreens";
import BasicMore from "./basic/BasicScreens";
import { featureEnabled } from "../../../lib/featureFlags";
import FeatureUnavailable from "./FeatureUnavailable";
import { AdvisorHub, PlanHub, ProfileHub } from "./hubs/FinvaHubs";
import FinancialDisclaimer from "../components/FinancialDisclaimer";

export function createFinvaFeatureRegistry({ user, plan, navigate, onUserChange, onLogout, featureFlags }) {
  const gated = (flagKey, component) => featureEnabled(featureFlags, flagKey) ? component : <FeatureUnavailable flags={featureFlags} flagKey={flagKey}/>;
  const vipEnabled = featureEnabled(featureFlags, "vip_intelligence");
  const advisory = (component, kind = "strategy") => <>{component}<FinancialDisclaimer kind={kind}/></>;
  return {
    overview: plan === "vip" && vipEnabled ? <VipScreens view="dashboard" user={user} onNavigate={navigate} /> : <FinvaOverview user={user} plan={plan} onNavigate={navigate} />,
    finance: <Finance plan={plan} onNavigate={navigate} />,
    plan: <PlanHub plan={plan} navigate={navigate} />,
    advisor: <AdvisorHub plan={plan} navigate={navigate} />,
    profile: <ProfileHub plan={plan} navigate={navigate} onLogout={onLogout} />,
    debts: <Debts plan={plan} />,
    strategy: advisory(plan === "vip" ? gated("vip_intelligence", <VipStrategy />) : <StrategyBasic plan={plan} />),
    gmail: plan === "vip" ? gated("gmail_automation", <GmailAutomation />) : <SettingsPage user={user} onUserChange={onUserChange} onLogout={onLogout} />,
    goals: plan === "vip" ? <VipScreens view="goal" user={user} onNavigate={navigate} /> : <Goals plan={plan} />,
    savings: <Goals plan={plan} initialView="savings" />,
    transactions: <Transactions plan={plan} />,
    situation: <FinancialSituation plan={plan} onNavigate={navigate} />,
    more: plan === "free" ? <FreeMore onNavigate={navigate} onLogout={onLogout} /> : plan === "basic" ? <BasicMore onNavigate={navigate} onLogout={onLogout} /> : <VipScreens view="more" user={user} onNavigate={navigate} onLogout={onLogout} />,
    settings: plan === "free" ? <FreeSettings user={user} onNavigate={navigate} onLogout={onLogout} /> : <SettingsPage user={user} onUserChange={onUserChange} onLogout={onLogout} />,
    "plan-settings": <SettingsPage user={user} onUserChange={onUserChange} onLogout={onLogout} />,
    budget: <Budget plan={plan} />,
    calendar: <FinancialCalendar plan={plan} />,
    recurring: <Recurring plan={plan} />,
    reports: gated("advanced_reports", <Reports plan={plan} />),
    monthly: <MonthlySummary />,
    feedback: <Feedback />,
    "vip-recommendation": advisory(gated("vip_intelligence", <VipScreens view="recommendation" user={user} onNavigate={navigate} />)),
    "vip-projections": advisory(gated("vip_intelligence", <VipScreens view="projections" user={user} onNavigate={navigate} />)),
    "vip-projection-detail": advisory(gated("vip_intelligence", <VipScreens view="projection-detail" user={user} onNavigate={navigate} />)),
    "vip-scenarios": advisory(gated("vip_intelligence", <VipScreens view="scenarios" user={user} onNavigate={navigate} />)),
    "vip-reality": gated("vip_intelligence", <VipScreens view="reality" user={user} onNavigate={navigate} />),
    "vip-monthly-review": advisory(gated("vip_intelligence", <VipScreens view="monthly-review" user={user} onNavigate={navigate} />)),
    "vip-today": gated("vip_intelligence", <VipScreens view="today" user={user} onNavigate={navigate} />),
    "vip-emergency": gated("vip_intelligence", <VipScreens view="emergency" user={user} onNavigate={navigate} />),
    "vip-aguinaldo": plan === "vip" ? advisory(gated("gmail_automation", <VipScreens view="aguinaldo" user={user} onNavigate={navigate} />), "aguinaldo") : <SettingsPage user={user} onUserChange={onUserChange} onLogout={onLogout} />,
    "vip-preferences": gated("vip_intelligence", <VipScreens view="preferences" user={user} onNavigate={navigate} />),
  };
}
