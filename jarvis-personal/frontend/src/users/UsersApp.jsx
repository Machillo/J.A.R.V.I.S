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
import { supabase } from "../lib/supabase";
import "./users.css";

export default function UsersApp({ user, onUserChange }) {
  const [page, setPage] = useState("overview");
  const plan = user?.subscription?.plan || "free";

  useEffect(() => {
    const scroller = document.querySelector(".users-app");
    if (scroller) scroller.scrollTo({ top: 0, left: 0, behavior: "auto" });
    else window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [page]);

  const pages = {
    overview: <Dashboard user={user} plan={plan} onNavigate={setPage} />,
    finance: <Finance />,
    debts: <Debts plan={plan} />,
    strategy: <StrategyBasic plan={plan} />,
    goals: <Goals plan={plan} />,
    transactions: <Transactions />,
    situation: <FinancialSituation plan={plan} onNavigate={setPage} />,
    settings: <SettingsPage user={user} onUserChange={onUserChange} />,
    budget: <Budget />,
    calendar: <FinancialCalendar />,
    recurring: <Recurring />,
    reports: <Reports />,
    monthly: <MonthlySummary />,
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
          {pages[page] || pages.overview}
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
