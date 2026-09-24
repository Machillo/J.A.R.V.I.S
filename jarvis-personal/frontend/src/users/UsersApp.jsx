import { useEffect, useState } from "react";
import AppErrorBoundary from "../components/AppErrorBoundary";
import { openSupport } from "../lib/apiErrors";
import NativeProductHeader from "../ui/native/NativeProductHeader";
import NativeProductShell from "../ui/native/NativeProductShell";
import { detectNativePlatform } from "../ui/native/platform";
import { createFinvaFeatureRegistry } from "../products/finva/features/registry";
import FinvaNavigation from "../products/finva/navigation/FinvaNavigation";
import useFinvaNavigation from "../products/finva/navigation/useFinvaNavigation";
import { completeVipMailConnection, getPlatformHealth, trackProductEvent } from "./services/jarvisApi";
import { MAIL_OAUTH_RETURN_EVENT, captureMailOAuthReturns, redeemPendingMailOAuth } from "../lib/mailOAuth";
import { supabase } from "../lib/supabase";
import { trackScreen } from "../lib/telemetry";
import { tx } from "../lib/locale";
import { flushPendingOperations, getPendingOperationCount } from "../lib/operationRecovery";
import "./users.css";
import "./finva-theme.css";
import "./finva-progressive.css";
import "../products/finva/styles/free.css";
import "../products/finva/styles/basic-figma.css";
import "../products/finva/styles/vip-figma.css";
import "../products/finva/styles/account-actions.css";
import ReleaseUpdateNotice from "../components/ReleaseUpdateNotice";
import { dismissRelease, isReleaseDismissed } from "../lib/releasePolicy";
import { cachedFeatureFlags, featureDisabledMessage, featureEnabled, getOperationalFeatureFlags } from "../lib/featureFlags";
import ProgressiveProfileNudge from "./components/ProgressiveProfileNudge";

export default function UsersApp({ user, onUserChange, releasePolicy }) {
  const initialPage = window.sessionStorage.getItem("finva:support-context") ? "feedback" : "overview";
  const { page, navigate } = useFinvaNavigation(initialPage);
  const [accessNotice, setAccessNotice] = useState(user?.subscription?.access_notice || null);
  const [apiIssue, setApiIssue] = useState(null);
  const [localHealth, setLocalHealth] = useState(() => navigator.onLine ? "operational" : "offline");
  const [platformHealth, setPlatformHealth] = useState("operational");
  const [pendingOperations, setPendingOperations] = useState(0);
  const [recoveryNotice, setRecoveryNotice] = useState("");
  const [releaseDismissed, setReleaseDismissed] = useState(() => isReleaseDismissed(releasePolicy));
  const [featureFlags, setFeatureFlags] = useState(() => cachedFeatureFlags());
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
    const open = () => navigate("feedback");
    const failed = (event) => { setApiIssue(event.detail || {}); setLocalHealth(navigator.onLine ? "degraded" : "offline"); };
    const reported = (event) => setApiIssue((current) => current ? { ...current, reported: true, publicId: event.detail?.public_id } : current);
    const recovered = () => { if (navigator.onLine) setLocalHealth("operational"); };
    const queueChanged = (event) => setPendingOperations(Number(event.detail?.pending || 0));
    const operationRecovered = (event) => {
      setPendingOperations(Number(event.detail?.pending || 0));
      setRecoveryNotice("recovered");
      window.setTimeout(() => setRecoveryNotice(""), 5_000);
    };
    const operationFailed = (event) => {
      setPendingOperations(Number(event.detail?.pending || 0));
      setRecoveryNotice("failed");
    };
    const offline = () => setLocalHealth("offline");
    const online = () => {
      setLocalHealth("recovering");
      flushPendingOperations();
      getPlatformHealth().then((health) => { setPlatformHealth(health.status || "operational"); setLocalHealth("operational"); }).catch(() => setLocalHealth("degraded"));
    };
    window.addEventListener("finva:open-support", open);
    window.addEventListener("finva:api-error", failed);
    window.addEventListener("finva:incident-reported", reported);
    window.addEventListener("finva:api-recovered", recovered);
    window.addEventListener("finva:operation-queue-changed", queueChanged);
    window.addEventListener("finva:operation-recovered", operationRecovered);
    window.addEventListener("finva:operation-recovery-failed", operationFailed);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    getPlatformHealth().then((health) => setPlatformHealth(health.status || "operational")).catch(() => setLocalHealth(navigator.onLine ? "degraded" : "offline"));
    getPendingOperationCount().then(setPendingOperations).catch(() => {});
    flushPendingOperations();
    return () => {
      window.removeEventListener("finva:open-support", open);
      window.removeEventListener("finva:api-error", failed);
      window.removeEventListener("finva:incident-reported", reported);
      window.removeEventListener("finva:api-recovered", recovered);
      window.removeEventListener("finva:operation-queue-changed", queueChanged);
      window.removeEventListener("finva:operation-recovered", operationRecovered);
      window.removeEventListener("finva:operation-recovery-failed", operationFailed);
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
    };
  }, [navigate]);

  // Mail OAuth returns by deep link, even when the app was relaunched from it:
  // this signed-in session redeems the one-time completion, then shows the result.
  // A completion interrupted by the network is retried when the app is back.
  useEffect(() => {
    captureMailOAuthReturns();
    const redeem = () => redeemPendingMailOAuth(completeVipMailConnection).then((outcome) => { if (outcome) navigate("gmail"); });
    const redeemWhenVisible = () => { if (document.visibilityState === "visible") redeem(); };
    redeem();
    window.addEventListener(MAIL_OAUTH_RETURN_EVENT, redeem);
    window.addEventListener("online", redeem);
    document.addEventListener("visibilitychange", redeemWhenVisible);
    return () => {
      window.removeEventListener(MAIL_OAUTH_RETURN_EVENT, redeem);
      window.removeEventListener("online", redeem);
      document.removeEventListener("visibilitychange", redeemWhenVisible);
    };
  }, [navigate]);

  useEffect(() => { if (user?.subscription?.access_notice) setAccessNotice(user.subscription.access_notice); }, [user?.subscription?.access_notice]);
  useEffect(() => { setReleaseDismissed(isReleaseDismissed(releasePolicy)); }, [releasePolicy]);
  useEffect(() => {
    let active = true;
    const refresh = () => getOperationalFeatureFlags().then((flags) => { if (active) setFeatureFlags(flags); });
    const visible = () => { if (document.visibilityState === "visible") refresh(); };
    refresh();
    const interval = window.setInterval(refresh, 60_000);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", visible);
    return () => { active=false;window.clearInterval(interval);window.removeEventListener("online",refresh);document.removeEventListener("visibilitychange",visible); };
  }, []);
  const logout = () => supabase.auth.signOut({ scope: "local" });
  const pages = createFinvaFeatureRegistry({ user, plan, navigate, onUserChange, onLogout: logout, featureFlags });
  const freeTitles = {
    overview: tx("Hola", "Hello") + `, ${(user?.display_name || user?.email || tx("bienvenido", "welcome")).split(" ")[0]}`,
    finance: tx("Movimientos", "Transactions"), debts: tx("Deudas", "Debts"), goals: tx("Metas", "Goals"),
    more: tx("Ahorro y más", "Savings & more"), settings: tx("Ajustes", "Settings"),
    savings: tx("Ahorros", "Savings"),
    transactions: tx("Historial", "History"), situation: tx("Situación financiera", "Financial situation"),
    monthly: tx("Resumen mensual", "Monthly summary"), feedback: tx("Ayuda", "Help"), advisor: tx("Asesor", "Advisor"),
  };
  const basicTitles = {
    overview: tx("Hola", "Hello") + `, ${(user?.display_name || user?.email || tx("bienvenido", "welcome")).split(" ")[0]}`, finance: tx("Movimientos", "Transactions"), debts: tx("Deudas", "Debts"), goals: tx("Metas", "Goals"),
    more: tx("Más", "More"), budget: tx("Presupuesto", "Budget"), calendar: tx("Calendario financiero", "Financial calendar"),
    recurring: tx("Recurrentes", "Recurring"), reports: tx("Reportes", "Reports"), strategy: tx("Estrategia", "Strategy"),
    situation: tx("Situación financiera", "Financial situation"), transactions: tx("Historial", "History"), monthly: tx("Resumen mensual", "Monthly summary"),
    settings: tx("Ajustes", "Settings"), feedback: tx("Ayuda", "Help"), advisor: tx("Asesor", "Advisor"),
  };
  const customHeader = plan === "free" || plan === "basic";
  const healthMode = localHealth === "operational" ? platformHealth : localHealth;

  return (
    <NativeProductShell product="finva" platform={platform} plan={plan} className="users-app">
      <div className="app mobile-app-shell">
        <NativeProductHeader
          product="DINCR"
          subtitle={plan === "free" ? tx("Gratis", "Free") : plan.toUpperCase()}
          eyebrow={plan === "free" ? (page === "more" || page === "settings" ? "DINCR · FREE" : "DINCR") : plan === "basic" ? "DINCR · BASIC" : undefined}
          title={plan === "free" ? (freeTitles[page] || "DINCR") : plan === "basic" ? (basicTitles[page] || "DINCR") : undefined}
          variant={customHeader ? plan : ""}
          avatar={(user?.display_name || user?.email || "U").slice(0, 1).toUpperCase()}
          onProfile={() => navigate("settings")}
        />
        <main className="content mobile-content native-scroll-content">
          {releasePolicy?.status === "optional" && !releaseDismissed && <ReleaseUpdateNotice policy={releasePolicy} onDismiss={() => { dismissRelease(releasePolicy); setReleaseDismissed(true); }} />}
          {featureFlags && !featureEnabled(featureFlags,"financial_writes") && <aside className="finva-health-mode finva-health-mode--degraded" role="status"><div><strong>{tx("Cambios temporalmente pausados", "Changes temporarily paused")}</strong><span>{featureDisabledMessage(featureFlags,"financial_writes",tx("es","en"))}</span></div></aside>}
          {accessNotice && <aside className="subscription-ended-banner" role="status"><div><strong>{accessNotice.title}</strong><span>{accessNotice.message}</span></div><button type="button" onClick={() => setAccessNotice(null)}>{tx("Entendido", "Got it")}</button></aside>}
          {healthMode !== "operational" && <aside className={`finva-health-mode finva-health-mode--${healthMode}`} role="status"><div><strong>{healthMode === "offline" ? tx("Sin conexión", "Offline") : healthMode === "recovering" ? tx("Reconectando…", "Reconnecting…") : healthMode === "major_outage" ? tx("Interrupción temporal", "Temporary outage") : tx("Modo degradado", "Degraded mode")}</strong><span>{healthMode === "offline" ? tx("Podés consultar lo cargado. Los cambios compatibles quedarán guardados en este dispositivo hasta reconectar.", "You can view loaded data. Supported changes will remain on this device until reconnection.") : tx("Algunas funciones pueden tardar. DINCR está intentando recuperarse y ya conserva el diagnóstico.", "Some features may be slow. DINCR is recovering and has preserved the diagnostic context.")}</span></div><button type="button" onClick={() => navigate("feedback")}>{tx("Ver estado", "View status")}</button></aside>}
          {pendingOperations > 0 && <aside className="finva-operation-recovery finva-operation-recovery--pending" role="status"><div><strong>{tx("Cambio protegido", "Change protected")}</strong><span>{tx(`${pendingOperations} cambio${pendingOperations === 1 ? "" : "s"} pendiente${pendingOperations === 1 ? "" : "s"}. Se enviará${pendingOperations === 1 ? "" : "n"} automáticamente.`, `${pendingOperations} pending change${pendingOperations === 1 ? "" : "s"}. DINCR will send ${pendingOperations === 1 ? "it" : "them"} automatically.`)}</span></div></aside>}
          {recoveryNotice && pendingOperations === 0 && <aside className={`finva-operation-recovery finva-operation-recovery--${recoveryNotice}`} role="status"><div><strong>{recoveryNotice === "recovered" ? tx("Cambio recuperado", "Change recovered") : tx("Revisá el cambio pendiente", "Review the pending change")}</strong><span>{recoveryNotice === "recovered" ? tx("DINCR lo guardó una sola vez al volver la conexión.", "DINCR saved it exactly once after reconnecting.") : tx("El servidor rechazó el cambio; abrí la sección e intentá nuevamente.", "The server rejected the change; open the section and try again.")}</span></div></aside>}
          {apiIssue && <aside className="finva-api-help" role="alert"><div><strong>{apiIssue.reported ? tx("DINCR ya avisó a soporte", "DINCR already notified support") : tx("Algo no cargó", "Something didn’t load")}</strong><span>{apiIssue.reported ? `${tx("Referencia", "Reference")}: ${apiIssue.publicId}` : tx("Intentamos recuperarlo automáticamente. Si continúa, guardaremos el diagnóstico.", "We tried to recover automatically. If it continues, we'll save the diagnosis.")}</span></div><button className="finva-api-help-support" type="button" onClick={() => { openSupport({ kind: "problem", ...apiIssue }); setApiIssue(null); }}>{tx("Abrir chat", "Open chat")}</button><button className="finva-api-help-close" type="button" aria-label={tx("Cerrar aviso", "Close notice")} onClick={() => setApiIssue(null)}>×</button></aside>}
          <ProgressiveProfileNudge user={user} plan={plan} page={page} onNavigate={navigate}/>
          <AppErrorBoundary resetKey={page} screen={page}>{pages[page] || pages.overview}</AppErrorBoundary>
        </main>
        <FinvaNavigation page={page} plan={plan} onNavigate={navigate} onLogout={logout} featureFlags={featureFlags}/>
      </div>
    </NativeProductShell>
  );
}
