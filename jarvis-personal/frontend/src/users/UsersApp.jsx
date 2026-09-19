import { useEffect, useState } from "react";
import AppErrorBoundary from "../components/AppErrorBoundary";
import { openSupport } from "../lib/apiErrors";
import NativeProductHeader from "../ui/native/NativeProductHeader";
import NativeProductShell from "../ui/native/NativeProductShell";
import { detectNativePlatform } from "../ui/native/platform";
import { createFinvaFeatureRegistry } from "../products/finva/features/registry";
import FinvaNavigation from "../products/finva/navigation/FinvaNavigation";
import { trackProductEvent } from "./services/jarvisApi";
import { supabase } from "../lib/supabase";
import { trackScreen } from "../lib/telemetry";
import { tx } from "../lib/locale";
import "./users.css";
import "./finva-theme.css";
import "./finva-progressive.css";
import "../products/finva/styles/free.css";
import "../products/finva/styles/basic-figma.css";
import "../products/finva/styles/vip-figma.css";
import "../products/finva/styles/account-actions.css";

export default function UsersApp({ user, onUserChange }) {
  const [page, setPage] = useState(() => window.sessionStorage.getItem("finva:support-context") ? "feedback" : "overview");
  const [accessNotice, setAccessNotice] = useState(user?.subscription?.access_notice || null);
  const [apiIssue, setApiIssue] = useState(null);
  const plan = user?.subscription?.plan || "free";
  const platform = detectNativePlatform();

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
    return () => { window.removeEventListener("finva:open-support", open); window.removeEventListener("finva:api-error", failed); };
  }, []);

  useEffect(() => { if (user?.subscription?.access_notice) setAccessNotice(user.subscription.access_notice); }, [user?.subscription?.access_notice]);
  const logout = () => supabase.auth.signOut({ scope: "local" });
  const pages = createFinvaFeatureRegistry({ user, plan, navigate: setPage, onUserChange, onLogout: logout });
  const freeTitles = {
    overview: tx("Hola", "Hello") + `, ${(user?.display_name || user?.email || tx("bienvenido", "welcome")).split(" ")[0]}`,
    finance: tx("Movimientos", "Transactions"), debts: tx("Deudas", "Debts"), goals: tx("Metas", "Goals"),
    more: tx("Ahorro y más", "Savings & more"), settings: tx("Ajustes", "Settings"),
    savings: tx("Ahorros", "Savings"),
    transactions: tx("Historial", "History"), situation: tx("Situación financiera", "Financial situation"),
    monthly: tx("Resumen mensual", "Monthly summary"), feedback: tx("Ayuda", "Help"),
  };
  const basicTitles = {
    overview: tx("Hola", "Hello") + `, ${(user?.display_name || user?.email || tx("bienvenido", "welcome")).split(" ")[0]}`, finance: tx("Movimientos", "Transactions"), debts: tx("Deudas", "Debts"), goals: tx("Metas", "Goals"),
    more: tx("Más", "More"), budget: tx("Presupuesto", "Budget"), calendar: tx("Calendario financiero", "Financial calendar"),
    recurring: tx("Recurrentes", "Recurring"), reports: tx("Reportes", "Reports"), strategy: tx("Estrategia", "Strategy"),
    situation: tx("Situación financiera", "Financial situation"), transactions: tx("Historial", "History"), monthly: tx("Resumen mensual", "Monthly summary"),
    settings: tx("Ajustes", "Settings"), feedback: tx("Ayuda", "Help"),
  };
  const customHeader = plan === "free" || plan === "basic";

  return (
    <NativeProductShell product="finva" platform={platform} plan={plan} className="users-app">
      <div className="app mobile-app-shell">
        <NativeProductHeader
          product="FINVA"
          subtitle={plan === "free" ? tx("Gratis", "Free") : plan.toUpperCase()}
          eyebrow={plan === "free" ? (page === "more" || page === "settings" ? "FINVA · FREE" : "FINVA") : plan === "basic" ? "FINVA · BASIC" : undefined}
          title={plan === "free" ? (freeTitles[page] || "FINVA") : plan === "basic" ? (basicTitles[page] || "FINVA") : undefined}
          variant={customHeader ? plan : ""}
          avatar={(user?.display_name || user?.email || "U").slice(0, 1).toUpperCase()}
          onProfile={() => setPage("settings")}
        />
        <main className="content mobile-content native-scroll-content">
          {accessNotice && <aside className="subscription-ended-banner" role="status"><div><strong>{accessNotice.title}</strong><span>{accessNotice.message}</span></div><button type="button" onClick={() => setAccessNotice(null)}>{tx("Entendido", "Got it")}</button></aside>}
          {apiIssue && <aside className="finva-api-help" role="alert"><div><strong>{tx("Algo no cargó", "Something didn’t load")}</strong><span>{tx("Podés intentar de nuevo o reportarlo.", "You can try again or report it.")}</span></div><button className="finva-api-help-support" type="button" onClick={() => { openSupport({ kind: "problem", ...apiIssue }); setApiIssue(null); }}>{tx("Reportar", "Report")}</button><button className="finva-api-help-close" type="button" aria-label={tx("Cerrar aviso", "Close notice")} onClick={() => setApiIssue(null)}>×</button></aside>}
          <AppErrorBoundary resetKey={page} screen={page}>{pages[page] || pages.overview}</AppErrorBoundary>
        </main>
        <FinvaNavigation page={page} plan={plan} onNavigate={setPage} onLogout={logout}/>
      </div>
    </NativeProductShell>
  );
}
