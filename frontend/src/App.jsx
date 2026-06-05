import { useEffect, useState } from "react";
import { LogOut, Menu, Mic, Send } from "lucide-react";

import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Finance from "./pages/Finance";
import Goals from "./pages/Goals";
import Memory from "./pages/Memory";
import Settings from "./pages/Settings";
import Transactions from "./pages/Transactions";
import Login from "./pages/Login";

import { askJarvis, getFinanceDashboard, getJarvisUsageToday, getMe, getStatus } from "./services/jarvisApi";
import { supabase } from "./lib/supabase";

export default function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 760);
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
    });

    return () => subscription.unsubscribe();
  }, []);

  const refreshAppData = async () => {
    if (!session) return;

    try {
      const [statusData, dashboardData, meData, usageData] = await Promise.all([
        getStatus(),
        getFinanceDashboard(),
        getMe(),
        getJarvisUsageToday(),
      ]);

      setStatus(statusData);
      setFinanceDashboard(dashboardData);
      setCurrentUser(meData);
      setAiUsage(usageData);
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
  };

  const speakText = (text) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-CR";
    speechSynthesis.speak(utterance);
  };

  const handleAskJarvis = async () => {
    const text = jarvisInput.trim();
    if (!text) return;

    setJarvisInput("");

    try {
      const response = await askJarvis(text);
      setJarvisResponse(response);

      const responseText =
        response?.response?.message || response?.message || "Respuesta recibida.";

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

  const handleVoiceInput = () => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("Tu navegador no soporta reconocimiento de voz.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "es-CR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    setIsListening(true);
    recognition.start();

    recognition.onresult = async (event) => {
      const text = event.results[0][0].transcript;
      setJarvisInput("");

      try {
        const response = await askJarvis(text);
        setJarvisResponse(response);

        const responseText =
          response?.response?.message ||
          response?.message ||
          `Intención detectada: ${response.intent}`;

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
        const errorText = "Ocurrió un error al comunicarme con Jarvis.";
        setChatHistory((current) => [
          ...current,
          { role: "user", text },
          { role: "jarvis", text: errorText },
        ].slice(-8));
        speakText(errorText);
      }
    };

    recognition.onerror = () => {
      setIsListening(false);
      speakText("No pude escucharte correctamente.");
    };

    recognition.onend = () => {
      setIsListening(false);
    };
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
        <main className="main-shell expanded">
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

      case "goals":
        return <Goals dashboard={financeDashboard} />;

      case "transactions":
        return <Transactions />;

      case "memory":
        return <Memory />;

      case "settings":
        return <Settings status={status} />;

      default:
        return <Dashboard jarvisResponse={jarvisResponse} chatHistory={chatHistory} />;
    }
  };

  return (
    <div className="jarvis-app">
      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        currentUser={currentUser}
        aiUsage={aiUsage}
      />

      <main className={`main-shell ${sidebarOpen ? "" : "expanded"} ${activePage === "dashboard" ? "home-mode" : ""}`}>
        <header className="top-bar">
          <button className="menu-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>
            <Menu size={22} />
          </button>

          <div>
            <h1>RESUMEN GENERAL</h1>
            <p>Panorama financiero actual</p>
          </div>

          <div className="system-status">
            <span className="live-dot"></span>
            SISTEMA ACTIVO
          </div>

          <button className="logout-button" onClick={handleLogout}>
            <LogOut size={18} />
            <span className="logout-text">Salir</span>
          </button>
        </header>

        {renderPage()}

        <section className="jarvis-command-center">
          <input
            value={jarvisInput}
            onChange={(event) => setJarvisInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") handleAskJarvis();
            }}
            placeholder={userName ? `¿En qué puedo ayudarte, ${userName}?` : "¿En qué puedo ayudarte?"}
          />

          <button className="command-button" onClick={handleAskJarvis}>
            <Send size={20} />
          </button>

          <button
            className={`voice-orb ${isListening ? "listening" : ""}`}
            onClick={handleVoiceInput}
          >
            <Mic size={28} />
          </button>
        </section>
      </main>
    </div>
  );
}
