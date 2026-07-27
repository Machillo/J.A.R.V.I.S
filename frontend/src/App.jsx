import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Brain,
  Camera,
  ChevronRight,
  CreditCard,
  ChartNoAxesCombined,
  LogOut,
  MailSearch,
  HandCoins,
  Mic,
  Bot,
  ReceiptText,
  Send,
  Settings as SettingsIcon,
  Target,
  UserRound,
  Landmark,
} from "lucide-react";
import Dashboard from "./pages/Dashboard";
import Finance from "./pages/Finance";
import Goals from "./pages/Goals";
import Memory from "./pages/Memory";
import Settings from "./pages/Settings";
import Transactions from "./pages/Transactions";
import PremiumStrategy from "./pages/PremiumStrategy";
import AdditionalCards from "./pages/AdditionalCards";
import Emails from "./pages/Emails";
import Receivables from "./pages/Receivables";
import Login from "./pages/Login";

import { askJarvis, getFinanceDashboard, getJarvisPremiumStrategySummary, getJarvisUsageToday, getMe, getProfilePreferences, getStatus, updateProfilePreferences } from "./services/jarvisApi";
import { supabase } from "./lib/supabase";

const sanitizeCourtesy = (text = "") =>
  String(text || "")
    .replace(/Señor\s+[A-ZÁÉÍÓÚÑa-záéíóúñ0-9._%+-]+(?:@[A-ZÁÉÍÓÚÑa-záéíóúñ0-9.-]+)?[,:\s]*/gi, "Señor, ")
    .replace(/Señor,\s*Señor,\s*/gi, "Señor, ");

const appSections = {
  dashboard: { title: "J.A.R.V.I.S.", eyebrow: "Assistant" },
  strategy: { title: "Strategy", eyebrow: "Financial Director" },
  finance: { title: "Finance", eyebrow: "Financial Center" },
  receivables: { title: "Receivables", eyebrow: "People & Payments" },
  chats: { title: "Data Tools", eyebrow: "Imports & Movements" },
  emails: { title: "Correos", eyebrow: "Chats" },
  transactions: { title: "Transacciones", eyebrow: "Chats" },
  additionalCards: { title: "Tarjetas", eyebrow: "Chats" },
  profile: { title: "Settings", eyebrow: "Profile" },
  memory: { title: "Memory Core", eyebrow: "Config" },
  settings: { title: "Configuración", eyebrow: "Config" },
  goals: { title: "Metas", eyebrow: "Config" },
};

const getBottomGroup = (page) => {
  if (["emails", "transactions", "additionalCards", "chats"].includes(page)) return "profile";
  if (["memory", "settings", "goals", "profile"].includes(page)) return "profile";
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
  return (
    <section className="app-hub-page">
      <div className="app-section-card">
        <AppListItem icon={MailSearch} title="Correos" subtitle="Escanear, revisar y agregar a finanzas" onClick={() => navigatePage("emails")} />
        <AppListItem icon={ReceiptText} title="Transacciones" subtitle="Movimientos guardados" onClick={() => navigatePage("transactions")} />
        <AppListItem icon={CreditCard} title="Tarjetas adicionales" subtitle="Emily y Sidey" onClick={() => navigatePage("additionalCards")} />
      </div>
    </section>
  );
}

function ProfileHub({ navigatePage, userName, currentUser, aiUsage, onLogout, profilePreferences, onProfilePhotoChange }) {
  const avatarUrl = profilePreferences?.avatar_data_url || currentUser?.avatar_url || currentUser?.user_metadata?.avatar_url || "";

  return (
    <section className="app-profile-page">
      <div className="profile-hero">
        <label className="profile-photo-picker" aria-label="Cambiar foto de perfil">
          <input type="file" accept="image/*" onChange={onProfilePhotoChange} />
          <span className="profile-avatar large">
            {avatarUrl ? <img src={avatarUrl} alt="Kenneth" /> : <span>{(userName || "K").slice(0, 1).toUpperCase()}</span>}
          </span>
          <span className="profile-camera-badge"><Camera size={18} /></span>
        </label>
        <h1>{profilePreferences?.display_name || userName || "Kenneth"}</h1>
        <p>Memory Core y configuración de JARVIS</p>
      </div>

      <div className="app-section-card">
        <AppListItem icon={Brain} title="Memory Core" subtitle="Memoria y contexto personal" onClick={() => navigatePage("memory")} />
        <AppListItem icon={Target} title="Goals" subtitle="Objetivos y prioridades" onClick={() => navigatePage("goals")} />
        <AppListItem icon={SettingsIcon} title="System Settings" subtitle="Preferencias de JARVIS" onClick={() => navigatePage("settings")} />
      </div>

      <div className="app-section-card">
        <AppListItem icon={MailSearch} title="Email Monitor" subtitle="Correos bancarios detectados" onClick={() => navigatePage("emails")} />
        <AppListItem icon={ReceiptText} title="Transactions" subtitle="Historial completo e importaciones" onClick={() => navigatePage("transactions")} />
        <AppListItem icon={CreditCard} title="Additional Cards" subtitle="Tarjetas asociadas por persona" onClick={() => navigatePage("additionalCards")} />
      </div>

      <div className="app-section-card compact">
        <div className="app-info-row">
          <span>Uso IA hoy</span>
          <strong>{aiUsage ? `${Math.round(aiUsage.total_tokens || 0).toLocaleString("es-CR")} tokens` : "--"}</strong>
        </div>
        <button className="app-list-item danger" onClick={onLogout}>
          <span className="app-list-icon"><LogOut size={22} /></span>
          <span className="app-list-copy"><strong>Salir</strong></span>
        </button>
      </div>
    </section>
  );
}

function BottomNavigation({ activePage, navigatePage, currentUser, userName, profilePreferences }) {
  const activeGroup = getBottomGroup(activePage);
  const avatarUrl = profilePreferences?.avatar_data_url || currentUser?.avatar_url || currentUser?.user_metadata?.avatar_url || "";
  const items = [
    { id: "dashboard", label: "JARVIS", icon: Bot },
    { id: "strategy", label: "Strategy", icon: ChartNoAxesCombined },
    { id: "finance", label: "Finance", icon: Landmark },
    { id: "receivables", label: "Receivables", icon: HandCoins },
    { id: "profile", label: "Settings", icon: UserRound, avatar: true },
  ];

  return (
    <nav className="bottom-app-nav" aria-label="Navegación principal">
      {items.map((item) => {
        const Icon = item.icon;
        const isActive = activeGroup === item.id;

        return (
          <button
            key={item.id}
            className={`bottom-nav-item ${isActive ? "active" : ""}`}
            onClick={() => navigatePage(item.id)}
          >
            <span className="bottom-nav-icon">
              {item.avatar ? (
                <span className="profile-avatar small">
                  {avatarUrl ? <img src={avatarUrl} alt="Perfil" /> : <span>{(userName || "K").slice(0, 1).toUpperCase()}</span>}
                </span>
              ) : (
                <Icon size={27} />
              )}
            </span>
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export default function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [pageStack, setPageStack] = useState([]);
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
  const [currentUser, setCurrentUser] = useState(null);
  const [aiUsage, setAiUsage] = useState(null);
  const [strategySummary, setStrategySummary] = useState(null);
  const [profilePreferences, setProfilePreferences] = useState(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    // JARVIS keeps one visual identity. Theme switching was removed on purpose.
    localStorage.removeItem("jarvis-theme");
    document.documentElement.setAttribute("data-theme", "classic");
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
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setSessionLoaded(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setFinanceDashboard(null);
      setStatus(null);
      setJarvisResponse(null);
      setChatHistory([]);
      setCurrentUser(null);
      setAiUsage(null);
      setStrategySummary(null);
      setProfilePreferences(null);
    });

    return () => subscription.unsubscribe();
  }, []);

  const refreshAppData = async () => {
    if (!session) return;

    try {
      const [statusData, dashboardData, meData, usageData, strategyData, profileData] = await Promise.all([
        getStatus(),
        getFinanceDashboard(),
        getMe(),
        getJarvisUsageToday(),
        getJarvisPremiumStrategySummary().catch(() => null),
        getProfilePreferences().catch(() => null),
      ]);

      setStatus(statusData);
      setFinanceDashboard(dashboardData);
      setCurrentUser(meData);
      setAiUsage(usageData);
      setStrategySummary(strategyData);
      setProfilePreferences(profileData?.value || profileData || null);
    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    refreshAppData();
  }, [session]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setSession(null);
    setFinanceDashboard(null);
    setStatus(null);
    setJarvisResponse(null);
    setChatHistory([]);
    setCurrentUser(null);
    setAiUsage(null);
    setStrategySummary(null);
    setProfilePreferences(null);
  };

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

      if (response?.usage || response?.response?.usage) {
        setAiUsage(response?.usage || response?.response?.usage);
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
      if (response?.usage || response?.response?.usage) {
        setAiUsage(response?.usage || response?.response?.usage);
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
    return (
      <div className={`jarvis-app ${currentUser?.role === "owner" || currentUser?.role === "admin" ? "admin-user" : ""}`}>
        <main className="main-shell home-mode">
          <section className="jarvis-home chat-home idle">
            <h1>J.A.R.V.I.S.</h1>
            <p className="home-subtitle">Inicializando sesión...</p>
          </section>
        </main>
      </div>
    );
  }

  if (!session) {
    return <Login />;
  }

  const renderPage = () => {
    switch (activePage) {
      case "finance":
        return <Finance dashboard={financeDashboard} currentUser={currentUser} onRefresh={refreshAppData} />;

      case "receivables":
        return <Receivables onRefresh={refreshAppData} />;

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
        return <Emails onFinanceChanged={refreshAppData} />;

      case "settings":
        return <Settings status={status} />;

      case "chats":
        return <ChatsHub navigatePage={navigatePage} />;

      case "profile":
        return <ProfileHub navigatePage={navigatePage} userName={userName} currentUser={currentUser} aiUsage={aiUsage} onLogout={handleLogout} profilePreferences={profilePreferences} onProfilePhotoChange={handleProfilePhotoChange} />;

      default:
        return <Dashboard jarvisResponse={jarvisResponse} chatHistory={chatHistory} userName={userName} />;
    }
  };

  const currentSection = appSections[activePage] || appSections[getBottomGroup(activePage)] || appSections.dashboard;
  const showHeader = activePage !== "dashboard";

  return (
    <div className={`jarvis-app app-shell-v2 ${(keyboardOpen || commandInputFocused) ? "keyboard-open" : ""}`}>
      <main className={`main-shell app-main-v2 ${activePage === "dashboard" ? "home-mode" : ""}`}>
        {showHeader && (
          <header className="app-top-bar">
            <button className="app-back-button" type="button" onClick={handleBack} aria-label="Volver">
              <ArrowLeft size={24} />
            </button>
            <div>
              <span>{currentSection.eyebrow}</span>
              <h1>{currentSection.title}</h1>
            </div>
          </header>
        )}

        {renderPage()}

        {activePage === "dashboard" && (
          <section className="jarvis-command-center" aria-label="Comando principal de Jarvis">
            <input
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

            <button className="command-button" onClick={handleAskJarvis} aria-label="Enviar mensaje">
              <Send size={20} />
            </button>

            <button
              className={`voice-orb ${isListening ? "listening" : ""}`}
              onClick={handleVoiceInput}
              aria-label="Hablar con Jarvis"
            >
              <Mic size={28} />
            </button>
          </section>
        )}
      </main>

      <BottomNavigation activePage={activePage} navigatePage={navigatePage} currentUser={currentUser} userName={userName} profilePreferences={profilePreferences} />
    </div>
  );
}
