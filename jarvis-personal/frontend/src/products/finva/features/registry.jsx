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
import VipExperience from "../../../users/pages/VipExperience";
import { FreeMore, FreeSettings } from "./free/FreeScreens";

export function createFinvaFeatureRegistry({ user, plan, navigate, onUserChange, onLogout }) {
  return {
    overview: plan === "vip" ? <VipExperience view="dashboard" onNavigate={navigate} /> : <FinvaOverview user={user} plan={plan} onNavigate={navigate} />,
    finance: <Finance plan={plan} />,
    debts: <Debts plan={plan} />,
    strategy: plan === "vip" ? <VipExperience view="strategy" onNavigate={navigate} /> : <StrategyBasic plan={plan} />,
    gmail: plan === "vip" ? <GmailAutomation /> : <SettingsPage user={user} onUserChange={onUserChange} />,
    goals: <Goals plan={plan} />,
    savings: <Goals plan={plan} initialView="savings" />,
    transactions: <Transactions />,
    situation: <FinancialSituation plan={plan} onNavigate={navigate} />,
    more: plan === "free" ? <FreeMore onNavigate={navigate} onLogout={onLogout} /> : <SettingsPage user={user} onUserChange={onUserChange} />,
    settings: plan === "free" ? <FreeSettings user={user} onNavigate={navigate} onLogout={onLogout} /> : <SettingsPage user={user} onUserChange={onUserChange} />,
    "plan-settings": <SettingsPage user={user} onUserChange={onUserChange} />,
    budget: <Budget />,
    calendar: <FinancialCalendar />,
    recurring: <Recurring />,
    reports: <Reports />,
    monthly: <MonthlySummary />,
    feedback: <Feedback />,
    "vip-recommendation": <VipExperience view="recommendation" onNavigate={navigate} />,
    "vip-projections": <VipExperience view="projections" onNavigate={navigate} />,
    "vip-scenarios": <VipExperience view="scenarios" onNavigate={navigate} />,
    "vip-reality": <VipExperience view="reality" onNavigate={navigate} />,
    "vip-emergency": <VipExperience view="emergency" onNavigate={navigate} />,
    "vip-preferences": <VipExperience view="preferences" onNavigate={navigate} />,
  };
}
