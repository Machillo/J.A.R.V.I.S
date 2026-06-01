import { useEffect, useState } from "react";

import Sidebar from "./components/Sidebar";
import VoiceButton from "./components/VoiceButton";

import Dashboard from "./pages/Dashboard";
import Finance from "./pages/Finance";
import Goals from "./pages/Goals";
import Memory from "./pages/Memory";
import Settings from "./pages/Settings";

import { getStatus, askJarvis } from "./services/jarvisApi";

export default function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [status, setStatus] = useState(null);
  const [jarvisResponse, setJarvisResponse] = useState(null);
  const [isListening, setIsListening] = useState(false);

  useEffect(() => {
    let isMounted = true;

    async function fetchStatus() {
      try {
        const data = await getStatus();

        if (isMounted) {
          setStatus(data);
        }
      } catch (error) {
        console.error(error);
      }
    }

    fetchStatus();

    return () => {
      isMounted = false;
    };
  }, []);

  const speakText = (text) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-CR";
    speechSynthesis.speak(utterance);
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

      try {
        const response = await askJarvis(text);

        setJarvisResponse(response);

        const responseText =
          response?.response?.message || `Intención detectada: ${response.intent}`;

        speakText(responseText);
      } catch (error) {
        console.error(error);
        speakText("Ocurrió un error al comunicarme con Jarvis.");
      }
    };

    recognition.onerror = (event) => {
      console.error("Speech recognition error:", event.error);
      setIsListening(false);
      speakText("No pude escucharte correctamente.");
    };

    recognition.onend = () => {
      setIsListening(false);
    };
  };

  const renderPage = () => {
    switch (activePage) {
      case "finance":
        return <Finance />;

      case "goals":
        return <Goals />;

      case "memory":
        return <Memory />;

      case "settings":
        return <Settings status={status} />;

      default:
        return <Dashboard status={status} jarvisResponse={jarvisResponse} />;
    }
  };

  return (
    <div className="app">
      <Sidebar activePage={activePage} setActivePage={setActivePage} />

      <main className="main-content">
        {renderPage()}

        <div className="voice-zone">
          <VoiceButton onClick={handleVoiceInput} isListening={isListening} />

          <p>{isListening ? "Escuchando..." : "Presiona para hablar con Jarvis"}</p>
        </div>
      </main>
    </div>
  );
}