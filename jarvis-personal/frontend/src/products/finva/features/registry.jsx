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
import VipStrategy from "../../../users/pages/VipStrategy";

export function createFinvaFeatureRegistry({ user, plan, navigate, onUserChange }) {
  return {
    overview: <FinvaOverview user={user} plan={plan} onNavigate={navigate} />,
    finance: <Finance />,
    debts: <Debts plan={plan} />,
    strategy: plan === "vip" ? <VipStrategy /> : <StrategyBasic plan={plan} />,
    gmail: plan === "vip" ? <GmailAutomation /> : <SettingsPage user={user} onUserChange={onUserChange} />,
    goals: <Goals plan={plan} />,
    transactions: <Transactions />,
    situation: <FinancialSituation plan={plan} onNavigate={navigate} />,
    settings: <SettingsPage user={user} onUserChange={onUserChange} />,
    budget: <Budget />,
    calendar: <FinancialCalendar />,
    recurring: <Recurring />,
    reports: <Reports />,
    monthly: <MonthlySummary />,
    feedback: <Feedback />,
  };
}
