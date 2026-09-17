import { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Finance from "./pages/Finance";
import Debts from "./pages/Debts";
import StrategyBasic from "./pages/StrategyBasic";
import Goals from "./pages/Goals";
import Transactions from "./pages/Transactions";
import SettingsPage from "./pages/Settings";
import FinancialSituation from "./pages/FinancialSituation";
import Budget from "./pages/Budget";
import FinancialCalendar from "./pages/Calendar";
import Recurring from "./pages/Recurring";
import Reports from "./pages/Reports";
import MonthlySummary from "./pages/MonthlySummary";
import VipStrategy from "./pages/VipStrategy";
import GmailAutomation from "./pages/GmailAutomation";
import Feedback from "./pages/Feedback";
import AppErrorBoundary from "../components/AppErrorBoundary";
import { openSupport } from "../lib/apiErrors";
import { trackProductEvent } from "./services/jarvisApi";
import { supabase } from "../lib/supabase";
import { trackScreen } from "../lib/telemetry";
import "./users.css";
import "./finva-theme.css";

export default function UsersApp({ user, onUserChange }) {
  const [page, setPage] = useState(() => window.sessionStorage.getItem("finva:support-context") ? "feedback" : "overview");
  const [accessNotice, setAccessNotice] = useState(user?.subscription?.access_notice || null);
  const [apiIssue, setApiIssue] = useState(null);
  const plan = user?.subscription?.plan || "free";

  useEffect(() => {
    const scroller = document.querySelector(".users-app");
    if (scroller) scroller.scrollTo({ top: 0, left: 0, behavior: "auto" });
    else window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    const eventMap = { overview:"dashboard_opened", finance:"finance_opened", debts:"debts_opened", goals:"goals_opened", transactions:"transactions_opened", strategy:"strategy_opened", gmail:"gmail_automation_opened", budget:"budget_opened", calendar:"calendar_opened", recurring:"recurring_opened", reports:"reports_opened", settings:"settings_opened" };
    if (eventMap[page]) trackProductEvent({ event_name:eventMap[page], surface:page, success:true }).catch(()=>{});
    trackScreen(`finva_${page}`, "FinvaPage");
  }, [page]);

  useEffect(() => {
    const open = () => setPage("feedback");
    const failed = (event) => setApiIssue(event.detail || {});
    window.addEventListener("finva:open-support", open);
    window.addEventListener("finva:api-error", failed);
    return () => {
      window.removeEventListener("finva:open-support", open);
      window.removeEventListener("finva:api-error", failed);
    };
  }, []);

  useEffect(() => {
    if (user?.subscription?.access_notice) setAccessNotice(user.subscription.access_notice);
  }, [user?.subscription?.access_notice]);

  const pages = {
    overview: <Dashboard user={user} plan={plan} onNavigate={setPage} />,
    finance: <Finance />,
    debts: <Debts plan={plan} />,
    strategy: plan === "vip" ? <VipStrategy /> : <StrategyBasic plan={plan} />,
    gmail: plan === "vip" ? <GmailAutomation /> : <SettingsPage user={user} onUserChange={onUserChange} />,
    goals: <Goals plan={plan} />,
    transactions: <Transactions />,
    situation: <FinancialSituation plan={plan} onNavigate={setPage} />,
    settings: <SettingsPage user={user} onUserChange={onUserChange} />,
    budget: <Budget />,
    calendar: <FinancialCalendar />,
    recurring: <Recurring />,
    reports: <Reports />,
    monthly: <MonthlySummary />,
    feedback: <Feedback />,
  };

  return (
    <div className="users-app">
      <div className="app mobile-app-shell">
        <main className="content mobile-content">
          <header className="mobile-app-header">
            <div>
              <strong>FINVA</strong>
              <small>{plan === "free" ? "Gratis" : plan.toUpperCase()}</small>
            </div>
            <button className="profile-chip" type="button" onClick={() => setPage("settings")}>
              {(user?.display_name || user?.email || "U").slice(0, 1).toUpperCase()}
            </button>
          </header>
          {accessNotice && <aside className="subscription-ended-banner" role="status">
            <div><strong>{accessNotice.title}</strong><span>{accessNotice.message}</span></div>
            <button type="button" onClick={() => setAccessNotice(null)}>Entendido</button>
          </aside>}
          {apiIssue && <aside className="finva-api-help" role="alert">
            <div><strong>No pudimos completar esa acción</strong><span>Intentá nuevamente o envianos un reporte; agregaremos la referencia técnica automáticamente.</span></div>
            <button type="button" onClick={() => { openSupport({ kind: "problem", ...apiIssue }); setApiIssue(null); }}>Contactar soporte</button>
            <button type="button" aria-label="Cerrar aviso" onClick={() => setApiIssue(null)}>×</button>
          </aside>}
          <AppErrorBoundary resetKey={page} screen={page}>
            {pages[page] || pages.overview}
          </AppErrorBoundary>
        </main>
        <Sidebar
          page={page}
          plan={plan}
          onNavigate={setPage}
          onLogout={() => supabase.auth.signOut()}
        />
      </div>
    </div>
  );
}
