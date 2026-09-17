import { Brain, Send, Sparkles } from "lucide-react";

function formatJarvisResponse(data) {
  if (!data) return null;
  if (data.message) return data.message;
  return "Señor, análisis completado.";
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
          <p>Hola {userName || "Kenneth"}</p>
          <h1>J.A.R.V.I.S.</h1>
          <span>¿Qué hacemos ahora?</span>
        </div>
      </header>

      {hasResponse ? (
        <section className="jarvis-v2-section jarvis-home-v2-session">
          <div className="jarvis-v2-section-title">
            <h2>Sesión actual</h2>
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
          <span>Listo cuando usted lo esté.</span>
        </div>
      )}
    </section>
  );
}
