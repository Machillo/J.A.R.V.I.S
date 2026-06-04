import { useEffect, useState } from "react";
import { LogOut, Menu, Mic, Send } from "lucide-react";

import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Finance from "./pages/Finance";
import Goals from "./pages/Goals";
import Memory from "./pages/Memory";
import Settings from "./pages/Settings";
import Login from "./pages/Login";

import { askJarvis, getFinanceDashboard, getStatus } from "./services/jarvisApi";
import { supabase } from "./lib/supabase";

export default function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 760);
  const [status, setStatus] = useState(null);
  const [financeDashboard, setFinanceDashboard] = useState(null);
  const [jarvisInput, setJarvisInput] = useState("");
  const [jarvisResponse, setJarvisResponse] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const [session, setSession] = useState(null);
  const [sessionLoaded, setSessionLoaded] = useState(false);

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
    });

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) return;

    async function loadData() {
      try {
        const [statusData, dashboardData] = await Promise.all([
          getStatus(),
          getFinanceDashboard(),
        ]);

        setStatus(statusData);
        setFinanceDashboard(dashboardData);
      } catch (error) {
        console.error(error);
      }
    }

    loadData();
  }, [session]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setSession(null);
    setFinanceDashboard(null);
    setStatus(null);
    setJarvisResponse(null);
  };

  const speakText = (text) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-CR";
    speechSynthesis.speak(utterance);
  };

  const handleAskJarvis = async () => {
    if (!jarvisInput.trim()) return;

    try {
      const response = await askJarvis(jarvisInput);
      setJarvisResponse(response);

      const responseText =
        response?.response?.message || response?.message || "Respuesta recibida.";

      speakText(responseText);
      setJarvisInput("");
    } catch (error) {
      console.error(error);
      speakText("No pude comunicarme con Jarvis.");
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
      setJarvisInput(text);

      try {
        const response = await askJarvis(text);
        setJarvisResponse(response);

        const responseText =
          response?.response?.message ||
          response?.message ||
          `Intención detectada: ${response.intent}`;

        speakText(responseText);
      } catch (error) {
        console.error(error);
        speakText("Ocurrió un error al comunicarme con Jarvis.");
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

  if (!sessionLoaded) {
    return (
      <div className="jarvis-app">
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
        return <Finance dashboard={financeDashboard} />;

      case "goals":
        return <Goals dashboard={financeDashboard} />;

      case "memory":
        return <Memory />;

      case "settings":
        return <Settings status={status} />;

      default:
        return <Dashboard jarvisResponse={jarvisResponse} />;
    }
  };

  return (
    <div className="jarvis-app">
      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
      />

      <main className={`main-shell ${sidebarOpen ? "" : "expanded"}`}>
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
            Salir
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
            placeholder="¿En qué puedo ayudarte, Kenneth?"
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
