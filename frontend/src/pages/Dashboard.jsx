import { Brain, Send, Sparkles } from "lucide-react";

function formatJarvisResponse(data) {
  if (!data) return null;

  if (data.message) {
    return data.message;
  }

  return "Señor, análisis completado.";
}

export default function Dashboard({ jarvisResponse, chatHistory = [], userName = "Kenneth" }) {
  const responseText = formatJarvisResponse(jarvisResponse);
  const hasResponse = Boolean(responseText) || chatHistory.length > 0;

  return (
    <section className={`jarvis-home chat-home ${hasResponse ? "has-response" : "idle"}`}>
      <div className="jarvis-hero clean-chat-hero">
        <div className="jarvis-core-orb">
          <div className="orb-ring"></div>
          <div className="orb-center">
            <Brain size={52} />
          </div>
        </div>

        <p className="jarvis-greeting">Hola {userName || "Kenneth"}</p>
        <h1>J.A.R.V.I.S.</h1>
        <p className="home-subtitle">¿Qué hacemos ahora?</p>
      </div>

      {hasResponse && (
        <div className="jarvis-mini-chat">
          <div className="mini-chat-title">
            <span>Sesión actual</span>
            <Sparkles size={16} />
          </div>

          <div className="mini-chat-feed">
            {chatHistory.length > 0 ? (
              chatHistory.map((item, index) => (
                <div key={`${item.role}-${index}`} className={`mini-chat-line ${item.role}`}>
                  <span>{item.role === "user" ? <Send size={13} /> : <Sparkles size={13} />}</span>
                  <p>{item.text}</p>
                </div>
              ))
            ) : (
              <div className="mini-chat-line jarvis">
                <span><Sparkles size={13} /></span>
                <p>{responseText}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
