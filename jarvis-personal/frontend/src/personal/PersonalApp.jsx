import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Brain,
  Camera,
  ChevronRight,
  CreditCard,
  LogOut,
  MailSearch,
  Mic,
  ReceiptText,
  Send,
  Settings as SettingsIcon,
  Target,
  UsersRound,
  Activity,
  HandCoins,
} from "lucide-react";
import Dashboard from "../pages/Dashboard";
import Finance from "../pages/Finance";
import Goals from "../pages/Goals";
import Memory from "../pages/Memory";
import Settings from "../pages/Settings";
import Transactions from "../pages/Transactions";
import PremiumStrategy from "../pages/PremiumStrategy";
import AdditionalCards from "../pages/AdditionalCards";
// Owner connects financial mailboxes through the same OAuth flow as DINCR Users.
import GmailAutomation from "../users/pages/GmailAutomation";
import { completeVipMailConnection } from "../users/services/jarvisApi";
import { MAIL_OAUTH_RETURN_EVENT, captureMailOAuthReturns, redeemPendingMailOAuth } from "../lib/mailOAuth";
import Receivables from "../pages/Receivables";
import Investments from "../pages/Investments";
import Wealth from "../pages/Wealth";
import Businesses from "../pages/Businesses";
import FinancialAccounts from "../pages/FinancialAccounts";
import NetWorth from "../pages/NetWorth";
import FinancialTimeline from "../pages/FinancialTimeline";
import Reconciliation from "../pages/Reconciliation";
import FinancialDeterioration from "../pages/FinancialDeterioration";
import Login from "../pages/Login";
import UserManagement from "../pages/UserManagement";
import FinvaOnboarding from "../pages/FinvaOnboarding";
import ProfileSetup from "../pages/ProfileSetup";
import ProductOperations from "../pages/ProductOperations";
import MoneyControl from "../products/jarvis/pages/MoneyControl";
import { JarvisGlassCard, JarvisScreen } from "../products/jarvis/components/JarvisScreen";

import { askJarvis, getFinanceDashboard, getMe, getOwnerBridgeToken, getProfilePreferences, getStatus, setOwnerBridgeToken, updateProfilePreferences } from "../services/jarvisApi";
import { supabase } from "../lib/supabase";
import { recordError, trackScreen } from "../lib/telemetry";
import AppearanceSelector from "../components/AppearanceSelector";
import NativeProductShell from "../ui/native/NativeProductShell";
import { detectNativePlatform } from "../ui/native/platform";
import JarvisNavigation from "../products/jarvis/navigation/JarvisNavigation";
import { applyDocumentLanguage, deviceLanguage, t, tx } from "../lib/locale";

const sanitizeCourtesy = (text = "") =>
  String(text || "")
    .replace(/Señor\s+[A-ZÁÉÍÓÚÑa-záéíóúñ0-9._%+-]+(?:@[A-ZÁÉÍÓÚÑa-záéíóúñ0-9.-]+)?[,:\s]*/gi, "Señor, ")
    .replace(/Señor,\s*Señor,\s*/gi, "Señor, ");

const appSectionsFor = (language) => ({
  dashboard: { title: "DINCR Owner", eyebrow: language === "es" ? "Espacio interno" : "Internal space" },
  strategy: { title: t("nav.strategy", language), eyebrow: language === "es" ? "Director financiero" : "Financial Director" },
  finance: { title: t("nav.finance", language), eyebrow: language === "es" ? "Centro financiero" : "Financial Center" },
  receivables: { title: t("nav.receivables", language), eyebrow: language === "es" ? "Personas y pagos" : "People & Payments" },
  wealth: { title: t("nav.wealth", language), eyebrow: t("wealth.eyebrow", language) },
  investments: { title: t("nav.investments", language), eyebrow: language === "es" ? "Construcción patrimonial" : "Wealth Building" },
  businesses: { title: t("nav.businesses", language), eyebrow: language === "es" ? "Construcción patrimonial" : "Wealth Building" },
  financialAccounts: { title: t("nav.accounts", language), eyebrow: language === "es" ? "Registro financiero" : "Financial Ledger" },
  netWorth: { title: t("nav.netWorth", language), eyebrow: language === "es" ? "Patrimonio actual" : "Live Wealth" },
  financialTimeline: { title: t("nav.financialTimeline", language), eyebrow: language === "es" ? "Mapa de liquidez" : "Liquidity Map" },
  reconciliation: { title: t("nav.reconciliation", language), eyebrow: language === "es" ? "Control financiero" : "Financial Control" },
  deterioration: { title: t("nav.deterioration", language), eyebrow: language === "es" ? "Alerta temprana" : "Early Warning" },
  chats: { title: language === "es" ? "Herramientas de datos" : "Data Tools", eyebrow: language === "es" ? "Importaciones y movimientos" : "Imports & Movements" },
  moneyControl: { title: language === "es" ? "Control de dinero" : "Money Control", eyebrow: language === "es" ? "Más" : "More" },
  emails: { title: t("nav.emailMonitor", language), eyebrow: language === "es" ? "Datos" : "Data" },
  transactions: { title: t("nav.transactions", language), eyebrow: language === "es" ? "Datos" : "Data" },
  additionalCards: { title: t("nav.additionalCards", language), eyebrow: language === "es" ? "Datos" : "Data" },
  profile: { title: t("nav.settings", language), eyebrow: language === "es" ? "Perfil" : "Profile" },
  memory: { title: t("nav.memory", language), eyebrow: language === "es" ? "Configuración" : "Settings" },
  settings: { title: t("nav.settings", language), eyebrow: language === "es" ? "Configuración" : "Settings" },
  goals: { title: t("nav.goals", language), eyebrow: language === "es" ? "Configuración" : "Settings" },
  userManagement: { title: t("nav.manageUsers", language), eyebrow: language === "es" ? "Control de propietario" : "Owner Control" },
  productOperations: { title: t("nav.finvaOperations", language), eyebrow: "DINCR Beta" },
});

const getBottomGroup = (page) => {
  if (["emails", "transactions", "additionalCards", "chats", "moneyControl"].includes(page)) return "profile";
  if (["memory", "settings", "goals", "profile", "userManagement", "productOperations"].includes(page)) return "profile";
  if (["investments", "businesses", "netWorth", "financialTimeline", "reconciliation", "deterioration", "wealth"].includes(page)) return "wealth";
  return page;
};

function AppListItem({ icon: Icon, title, subtitle, onClick }) {
  return (
    <button className="app-list-item" onClick={onClick}>
      <span className="app-list-icon"><Icon size={24} /></span>
      <span className="app-list-copy">
        <strong>{title}</strong>
        {subtitle && <small>{subtitle}</small>}
      </span>
      <ChevronRight size={22} className="app-list-chevron" />
    </button>
  );
}

function ChatsHub({ navigatePage }) {
  const language = deviceLanguage();
  return (
    <section className="app-hub-page">
      <div className="app-section-card">
        <AppListItem icon={MailSearch} title={t("nav.emailMonitor", language)} subtitle={tx("Escanear, revisar y agregar a finanzas", "Scan, review, and add to finance", language)} onClick={() => navigatePage("emails")} />
        <AppListItem icon={ReceiptText} title={t("nav.transactions", language)} subtitle={tx("Movimientos guardados", "Saved transactions", language)} onClick={() => navigatePage("transactions")} />
        <AppListItem icon={CreditCard} title={t("nav.additionalCards", language)} subtitle={tx("Tarjetas asociadas por persona", "Cards linked by person", language)} onClick={() => navigatePage("additionalCards")} />
      </div>
    </section>
  );
}

function ProfileHub({ navigatePage, userName, currentUser, onLogout, profilePreferences, onProfilePhotoChange }) {
  const language = deviceLanguage();
  const avatarUrl = profilePreferences?.avatar_data_url || currentUser?.avatar_url || currentUser?.user_metadata?.avatar_url || "";

  return (
    <JarvisScreen eyebrow={tx("Perfil", "Profile", language)} title={profilePreferences?.display_name || userName || "Kenneth"} subtitle={tx("Tu identidad y preferencias", "Your identity and preferences", language)} className="profile-screen">
      <div className="profile-hero">
        <label className="profile-photo-picker" aria-label={tx("Cambiar foto de perfil", "Change profile photo", language)}>
          <input type="file" accept="image/*" onChange={onProfilePhotoChange} />
          <span className="profile-avatar large">
            {avatarUrl ? <img src={avatarUrl} alt="Kenneth" /> : <span>{(userName || "K").slice(0, 1).toUpperCase()}</span>}
          </span>
          <span className="profile-camera-badge"><Camera size={18} /></span>
        </label>
        <h1>{profilePreferences?.display_name || userName || "Kenneth"}</h1>
        <p>{currentUser?.email || sessionStorage.getItem("jarvis_user_email") || ""}</p>
      </div>

      <JarvisGlassCard as="div" className="profile-appearance-card">
        <div className="app-group-heading"><strong>{tx("Apariencia", "Appearance", language)}</strong><small>{tx("Oscuro · Automático", "Dark · Automatic", language)}</small></div>
        <AppearanceSelector compact />
      </JarvisGlassCard>

      <div className="profile-link-list">
        <AppListItem icon={Brain} title={t("nav.memory", language)} subtitle={tx("Memoria y contexto personal", "Memory and personal context", language)} onClick={() => navigatePage("memory")} />
        <AppListItem icon={Target} title={t("nav.goals", language)} subtitle={tx("Objetivos y prioridades", "Objectives and priorities", language)} onClick={() => navigatePage("goals")} />
        <AppListItem icon={SettingsIcon} title={t("nav.settings", language)} subtitle={tx("Preferencias de DINCR Owner", "DINCR Owner preferences", language)} onClick={() => navigatePage("settings")} />
        <AppListItem icon={HandCoins} title={tx("Datos financieros", "Financial data", language)} subtitle={tx("Control · Email · historial · tarjetas", "Control · Email · history · cards", language)} onClick={() => navigatePage("moneyControl")} />
        {currentUser?.role === "owner" && (
          <><AppListItem icon={UsersRound} title={t("nav.manageUsers", language)} subtitle={tx("Buscar cuentas y otorgar cortesías", "Find accounts and grant courtesy access", language)} onClick={() => navigatePage("userManagement")} />
          <AppListItem icon={Activity} title={t("nav.finvaOperations", language)} subtitle={tx("Promoción, pagos, uso y reportes", "Promotions, payments, usage, and reports", language)} onClick={() => navigatePage("productOperations")} /></>
        )}
      </div>

      <div className="profile-footer-actions">
        <button className="jarvis-danger-button" type="button" onClick={onLogout}>{t("nav.logout", language)}</button>
      </div>
    </JarvisScreen>
  );
}

export default function App() {
  const language = deviceLanguage();
  const appSections = appSectionsFor(language);
  const [activePage, setActivePage] = useState("dashboard");
  const [, setPageStack] = useState([]);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [commandInputFocused, setCommandInputFocused] = useState(false);
  const [status, setStatus] = useState(null);
  const [financeDashboard, setFinanceDashboard] = useState(null);
  const [jarvisInput, setJarvisInput] = useState("");
  const [jarvisResponse, setJarvisResponse] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [isListening, setIsListening] = useState(false);
  const [session, setSession] = useState(null);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [ownerBridgeMode, setOwnerBridgeMode] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [profilePreferences, setProfilePreferences] = useState(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "classic");
    applyDocumentLanguage(deviceLanguage());
  }, []);

  useEffect(() => {
    const updateViewport = () => {
      const viewport = window.visualViewport;
      const height = viewport?.height || window.innerHeight;
      const keyboardOffset = Math.max(0, window.innerHeight - height - (viewport?.offsetTop || 0));

      document.documentElement.style.setProperty("--app-vh", `${height}px`);
      document.documentElement.style.setProperty("--keyboard-offset", `${keyboardOffset}px`);
      setKeyboardOpen(keyboardOffset > 80);
    };

    updateViewport();
    window.visualViewport?.addEventListener("resize", updateViewport);
    window.visualViewport?.addEventListener("scroll", updateViewport);
    window.addEventListener("resize", updateViewport);

    return () => {
      window.visualViewport?.removeEventListener("resize", updateViewport);
      window.visualViewport?.removeEventListener("scroll", updateViewport);
      window.removeEventListener("resize", updateViewport);
    };
  }, []);


  useEffect(() => {
    let activeUserId = null;
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const incomingBridgeToken = hash.get("jarvis_owner_bridge");
    if (incomingBridgeToken) {
      setOwnerBridgeToken(incomingBridgeToken);
      setOwnerBridgeMode(true);
      window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.search}`);
      setSession({ user: { user_metadata: { full_name: "Kenneth" }, bridge: true } });
      setSessionLoaded(true);
      return;
    }

    const storedBridgeToken = getOwnerBridgeToken();
    if (storedBridgeToken) {
      setOwnerBridgeMode(true);
      setSession({ user: { user_metadata: { full_name: "Kenneth" }, bridge: true } });
      setSessionLoaded(true);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      activeUserId = data.session?.user?.id || null;
      setSession(data.session);
      setSessionLoaded(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      const nextUserId = nextSession?.user?.id || null;
      const identityChanged = event === "SIGNED_OUT" || (activeUserId !== null && activeUserId !== nextUserId);
      activeUserId = nextUserId;
      setSession(nextSession);
      if (identityChanged) {
        setFinanceDashboard(null);
        setStatus(null);
        setJarvisResponse(null);
        setChatHistory([]);
        setCurrentUser(null);
        setProfilePreferences(null);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const refreshAppData = async () => {
    if (!session) return;

    try {
      const meData = await getMe();
      setCurrentUser(meData);

      // New commercial users finish plan selection/onboarding before Personal modules load.
      if (meData?.role !== "owner" && !meData?.plan_selected) {
        return;
      }

      // Hydrate independent surfaces independently. A slow analytics/profile
      // request must never hold Finance or the shell hostage.
      getStatus().then(setStatus).catch((error) => recordError(error, "jarvis_status"));
      getFinanceDashboard().then(setFinanceDashboard).catch((error) => recordError(error, "jarvis_finance_dashboard"));
      getProfilePreferences()
        .then((profileData) => setProfilePreferences(profileData?.value || profileData || null))
        .catch(() => setProfilePreferences(null));
    } catch (error) {
      console.error(error);
      recordError(error, "jarvis_refresh_app_data");
    }
  };

  useEffect(() => {
    refreshAppData();
  }, [session]);

  useEffect(() => {
    trackScreen(`jarvis_${activePage}`, "JarvisPage");
    const frame = window.requestAnimationFrame(() => {
      const appScroller = document.querySelector(".jarvis-app.app-shell-v2");
      if (appScroller) {
        appScroller.scrollTo({ top: 0, left: 0, behavior: "auto" });
      } else {
        window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      }
    });

    return () => window.cancelAnimationFrame(frame);
  }, [activePage]);

  const handleLogout = async () => {
    if (ownerBridgeMode) {
      setOwnerBridgeToken("");
      setOwnerBridgeMode(false);
      const publicAppUrl = import.meta.env.VITE_JARVIS_PUBLIC_APP_URL || "http://localhost:5174";
      window.location.replace(publicAppUrl);
      return;
    }

    await supabase.auth.signOut();
    setSession(null);
    setFinanceDashboard(null);
    setStatus(null);
    setJarvisResponse(null);
    setChatHistory([]);
    setCurrentUser(null);
    setProfilePreferences(null);
  };

  // Mail OAuth returns by deep link, exactly as in DINCR Users: this signed-in
  // Owner session redeems the one-time completion, then shows its mailboxes.
  useEffect(() => {
    captureMailOAuthReturns();
    const redeem = () => redeemPendingMailOAuth(completeVipMailConnection).then((outcome) => { if (outcome) setActivePage("emails"); });
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
  }, []);

  const navigatePage = (nextPage) => {
    if (!nextPage || nextPage === activePage) return;
    setPageStack((stack) => [...stack, activePage].slice(-12));
    setActivePage(nextPage);
  };

  const handleBack = () => {
    setPageStack((stack) => {
      const nextStack = [...stack];
      const previous = nextStack.pop();
      const parentGroup = getBottomGroup(activePage);
      const fallback = parentGroup !== activePage ? parentGroup : "dashboard";
      setActivePage(previous || fallback);
      return nextStack;
    });
  };

  const resizeImageToDataUrl = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("No pude leer la imagen."));
    reader.onload = () => {
      const image = new Image();
      image.onerror = () => reject(new Error("La imagen no es válida."));
      image.onload = () => {
        const maxSize = 512;
        const scale = Math.min(1, maxSize / Math.max(image.width, image.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(image.width * scale));
        canvas.height = Math.max(1, Math.round(image.height * scale));
        const context = canvas.getContext("2d");
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", 0.82));
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });

  const handleProfilePhotoChange = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    try {
      const avatarDataUrl = await resizeImageToDataUrl(file);
      const result = await updateProfilePreferences({ avatar_data_url: avatarDataUrl });
      setProfilePreferences(result?.value || { ...(profilePreferences || {}), avatar_data_url: avatarDataUrl });
    } catch (error) {
      console.error(error);
      alert("No pude guardar la foto de perfil.");
    }
  };

  const speakText = (text) => {
    const normalized = sanitizeCourtesy(text);

    const utterance = new SpeechSynthesisUtterance(normalized);
    utterance.lang = "es-CR";
    utterance.rate = 0.86;
    utterance.pitch = 0.92;
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  };

  const handleAskJarvis = async () => {
    const text = jarvisInput.trim();
    if (!text) return;

    setJarvisInput("");

    try {
      const response = await askJarvis(text);
      setJarvisResponse(response);

      const responseText = sanitizeCourtesy(
        response?.response?.message || response?.message || "Respuesta recibida."
      );

      setChatHistory((current) => [
        ...current,
        { role: "user", text },
        { role: "jarvis", text: responseText },
      ].slice(-8));

      if (response?.status === "OK" && (response?.action_type?.startsWith("create_") || response?.action_type === "import_monthly_statement")) {
        await refreshAppData();
      }

      speakText(responseText);
    } catch (error) {
      console.error(error);
      const errorText = "No pude comunicarme con Jarvis.";
      setChatHistory((current) => [
        ...current,
        { role: "user", text },
        { role: "jarvis", text: errorText },
      ].slice(-8));
      speakText(errorText);
    }
  };

  const submitJarvisText = async (text) => {
    const cleanText = String(text || "").trim();
    if (!cleanText) return;
    setJarvisInput("");

    try {
      const response = await askJarvis(cleanText);
      setJarvisResponse(response);
      const responseText = sanitizeCourtesy(
        response?.response?.message || response?.message || `Intención detectada: ${response.intent}`
      );
      setChatHistory((current) => [
        ...current,
        { role: "user", text: cleanText },
        { role: "jarvis", text: responseText },
      ].slice(-8));
      if (response?.status === "OK" && (response?.action_type?.startsWith("create_") || response?.action_type === "import_monthly_statement")) {
        await refreshAppData();
      }
      speakText(responseText);
    } catch (error) {
      console.error(error);
      const errorText = "Ocurrió un error al comunicarme con Jarvis.";
      setChatHistory((current) => [
        ...current,
        { role: "user", text: cleanText },
        { role: "jarvis", text: errorText },
      ].slice(-8));
      speakText(errorText);
    }
  };

  const handleVoiceInput = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Tu navegador no soporta reconocimiento de voz.");
      return;
    }

    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "es-CR";
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;

    let finalTranscript = "";
    let currentTranscript = "";
    setIsListening(true);
    setJarvisInput("");

    recognition.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const chunk = event.results[index][0].transcript;
        if (event.results[index].isFinal) {
          finalTranscript += `${chunk} `;
        } else {
          interim += chunk;
        }
      }
      currentTranscript = `${finalTranscript}${interim}`.trim();
      setJarvisInput(currentTranscript);
    };

    recognition.onerror = () => {
      setIsListening(false);
      recognitionRef.current = null;
      speakText("No pude escucharte correctamente.");
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      const text = currentTranscript.trim() || finalTranscript.trim();
      if (text) submitJarvisText(text);
    };

    recognition.start();
  };

  const rawUserName =
    session?.user?.user_metadata?.full_name ||
    session?.user?.user_metadata?.display_name ||
    session?.user?.user_metadata?.name ||
    session?.user?.email?.split("@")[0] ||
    "";

  const userName = rawUserName.trim().split(/\s+/)[0] || "";

  if (!sessionLoaded) {
    return <main className="jarvis-boot-screen"><strong>DINCR Owner</strong><span>Inicializando sesión...</span></main>;
  }

  if (!session) {
    return <Login />;
  }

  if (!currentUser) {
    return <main className="jarvis-boot-screen"><strong>DINCR Owner</strong><span>Preparando tu espacio...</span></main>;
  }

  if (!currentUser.profile_setup_completed) {
    return <ProfileSetup user={currentUser} onComplete={(profile) => { setCurrentUser(profile); refreshAppData(); }} />;
  }

  if (currentUser.role !== "owner" && !currentUser.plan_selected) {
    return <FinvaOnboarding user={currentUser} onComplete={(profile) => { setCurrentUser(profile); refreshAppData(); }} />;
  }

  const renderPage = () => {
    switch (activePage) {
      case "finance":
        return <Finance dashboard={financeDashboard} currentUser={currentUser} onRefresh={refreshAppData} />;

      case "receivables":
        return <Receivables onRefresh={refreshAppData} />;

      case "wealth":
        return <Wealth navigatePage={navigatePage} />;
      case "financialAccounts":
        return <FinancialAccounts onFinanceChanged={refreshAppData} />;
      case "netWorth":
        return <NetWorth />;
      case "financialTimeline":
        return <FinancialTimeline />;
      case "reconciliation":
        return <Reconciliation />;
      case "deterioration":
        return <FinancialDeterioration />;

      case "investments":
        return <Investments />;

      case "businesses":
        return <Businesses />;

      case "goals":
        return <Goals dashboard={financeDashboard} />;

      case "transactions":
        return <Transactions />;

      case "memory":
        return <Memory />;

      case "strategy":
        return <PremiumStrategy />;

      case "additionalCards":
        return <AdditionalCards />;

      case "emails":
        return <GmailAutomation />;

      case "settings":
        return <Settings status={status} />;

      case "chats":
        return <ChatsHub navigatePage={navigatePage} />;
      case "moneyControl":
        return <MoneyControl onNavigate={navigatePage} />;

      case "userManagement":
        return <UserManagement />;
      case "productOperations":
        return <ProductOperations />;

      case "profile":
        return <ProfileHub navigatePage={navigatePage} userName={userName} currentUser={currentUser} onLogout={handleLogout} profilePreferences={profilePreferences} onProfilePhotoChange={handleProfilePhotoChange} />;

      default:
        return <Dashboard jarvisResponse={jarvisResponse} chatHistory={chatHistory} userName={userName} profilePreferences={profilePreferences} currentUser={currentUser} onOpenProfile={() => navigatePage("profile")} />;
    }
  };

  const currentSection = appSections[activePage] || appSections[getBottomGroup(activePage)] || appSections.dashboard;
  // "emails" renders the shared product mailbox screen, which relies on the shell back bar.
  const immersivePages = new Set(["moneyControl", "transactions", "additionalCards", "goals", "memory", "profile", "settings"]);
  const showHeader = activePage !== "dashboard" && !immersivePages.has(activePage);
  const platform = detectNativePlatform();
  const isStandalonePwa = window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone === true;

  return (
    <NativeProductShell product="jarvis" platform={platform} plan="personal" className={`jarvis-app app-shell-v2 ${isStandalonePwa ? "jarvis-pwa-standalone" : ""} ${(keyboardOpen || commandInputFocused) ? "keyboard-open" : ""}`}>
      <main className={`main-shell app-main-v2 ${activePage === "dashboard" ? "jarvis-home-layout" : ""}`}>
        {showHeader && (
          <header className="app-top-bar">
            <button className="app-back-button" type="button" onClick={handleBack} aria-label="Volver">
              <ArrowLeft size={24} />
            </button>
            <div>
              <span>{currentSection.eyebrow}</span>
              <h1>{currentSection.title}</h1>
            </div>
            <button className="app-logout-button" type="button" onClick={handleLogout} aria-label="Cerrar sesión" title="Cerrar sesión">
              <LogOut size={21} />
            </button>
          </header>
        )}

        {activePage !== "dashboard" ? (
          <div className={`native-screen-content native-screen-content--${activePage}`}>
            {renderPage()}
          </div>
        ) : renderPage()}

        {activePage === "dashboard" && (
          <section className="jarvis-home-command" aria-label="Comando principal de Jarvis">
            <input
              aria-label="Comando para JARVIS"
              value={jarvisInput}
              onChange={(event) => setJarvisInput(event.target.value)}
              onFocus={() => setCommandInputFocused(true)}
              onBlur={() => {
                window.setTimeout(() => setCommandInputFocused(false), 120);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleAskJarvis();
              }}
              placeholder={isListening ? "🎤 Escuchando..." : "Mensaje para Jarvis"}
              inputMode="text"
            />

            <button className="jarvis-home-send" onClick={handleAskJarvis} aria-label="Enviar mensaje">
              <Send size={20} />
            </button>

            <button
              className={`jarvis-home-voice ${isListening ? "listening" : ""}`}
              onClick={handleVoiceInput}
              aria-label="Hablar con Jarvis"
            >
              <Mic size={28} />
            </button>
          </section>
        )}
      </main>

      <JarvisNavigation activePage={activePage} onNavigate={navigatePage} currentUser={currentUser} userName={userName} profilePreferences={profilePreferences} onLogout={handleLogout} />
    </NativeProductShell>
  );
}
