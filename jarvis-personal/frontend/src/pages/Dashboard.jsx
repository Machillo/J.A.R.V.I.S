import { Brain, Send, Sparkles } from "lucide-react";
import { deviceLanguage } from "../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

function formatJarvisResponse(data) {
  if (!data) return null;
  if (data.message) return data.message;
  return tx("Señor, análisis completado.", "Sir, analysis complete.");
}

export default function Dashboard({ jarvisResponse, chatHistory = [], userName = "Kenneth" }) {
  const responseText = formatJarvisResponse(jarvisResponse);
  const hasResponse = Boolean(responseText) || chatHistory.length > 0;
  const latestMessages = chatHistory.slice(-6);

  return (
    <section className={`jarvis-v2-screen jarvis-home-v2 ${hasResponse ? "has-response" : "idle"}`}>
      <header className="jarvis-home-v2-hero">
        <div className="jarvis-home-v2-mark" aria-hidden="true"><Brain size={24} /></div>
        <div>
          <p>{tx("Hola", "Hello")} {userName || "Kenneth"}</p>
          <h1>J.A.R.V.I.S.</h1>
          <span>{tx("¿Qué hacemos ahora?", "What shall we do now?")}</span>
        </div>
      </header>

      {hasResponse ? (
        <section className="jarvis-v2-section jarvis-home-v2-session">
          <div className="jarvis-v2-section-title">
            <h2>{tx("Sesión actual", "Current session")}</h2>
            <Sparkles size={15} />
          </div>
          <div className="jarvis-home-v2-feed">
            {latestMessages.length > 0 ? latestMessages.map((item, index) => (
              <div key={`${item.role}-${index}`} className={`jarvis-home-v2-message ${item.role}`}>
                <span>{item.role === "user" ? <Send size={13} /> : <Sparkles size={13} />}</span>
                <p>{item.text}</p>
              </div>
            )) : (
              <div className="jarvis-home-v2-message jarvis">
                <span><Sparkles size={13} /></span>
                <p>{responseText}</p>
              </div>
            )}
          </div>
        </section>
      ) : (
        <div className="jarvis-home-v2-idle">
          <Sparkles size={16} />
          <span>{tx("Listo cuando usted lo esté.", "Ready when you are.")}</span>
        </div>
      )}
    </section>
  );
}
