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
  const pages = createFinvaFeatureRegistry({ user, plan, navigate: setPage, onUserChange });

  return (
    <NativeProductShell product="finva" platform={platform} plan={plan} className="users-app">
      <div className="app mobile-app-shell">
        <NativeProductHeader product="FINVA" subtitle={plan === "free" ? tx("Gratis", "Free") : plan.toUpperCase()} avatar={(user?.display_name || user?.email || "U").slice(0, 1).toUpperCase()} onProfile={() => setPage("settings")}/>
        <main className="content mobile-content native-scroll-content">
          {accessNotice && <aside className="subscription-ended-banner" role="status"><div><strong>{accessNotice.title}</strong><span>{accessNotice.message}</span></div><button type="button" onClick={() => setAccessNotice(null)}>{tx("Entendido", "Got it")}</button></aside>}
          {apiIssue && <aside className="finva-api-help" role="alert"><div><strong>{tx("Algo no cargó", "Something didn’t load")}</strong><span>{tx("Podés intentar de nuevo o reportarlo.", "You can try again or report it.")}</span></div><button className="finva-api-help-support" type="button" onClick={() => { openSupport({ kind: "problem", ...apiIssue }); setApiIssue(null); }}>{tx("Reportar", "Report")}</button><button className="finva-api-help-close" type="button" aria-label={tx("Cerrar aviso", "Close notice")} onClick={() => setApiIssue(null)}>×</button></aside>}
          <AppErrorBoundary resetKey={page} screen={page}>{pages[page] || pages.overview}</AppErrorBoundary>
        </main>
        <FinvaNavigation page={page} plan={plan} onNavigate={setPage} onLogout={() => supabase.auth.signOut()}/>
      </div>
    </NativeProductShell>
  );
}
