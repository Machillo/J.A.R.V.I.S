import { Brain, Keyboard, Mic, Plug, Send, Sparkles } from "lucide-react";

function formatJarvisResponse(data) {
  if (!data) return null;

  if (data.message) {
    return data.message;
  }

  return "Señor, análisis completado.";
}

export default function Dashboard({ jarvisResponse, chatHistory = [] }) {
  const responseText = formatJarvisResponse(jarvisResponse);
  const hasResponse = Boolean(responseText) || chatHistory.length > 0;

  return (
    <section className={`jarvis-home chat-home ${hasResponse ? "has-response" : "idle"}`}>
      <div className="jarvis-hero">
        <div className="jarvis-core-orb">
          <div className="orb-ring"></div>
          <div className="orb-center">
            <Brain size={52} />
          </div>
        </div>

        <h1>J.A.R.V.I.S.</h1>

        <p className="home-subtitle">
          Sistema personal activo. Finanzas, metas, memoria y automatización.
        </p>

        {!hasResponse && (
          <div className="home-status-grid">
            <div className="home-status-card accent-cyan">
              <span className="status-icon"><Plug size={30} /></span>
              <span>Sistema</span>
              <strong>Activo</strong>
            </div>

            <div className="home-status-card accent-magenta">
              <span className="status-icon"><Brain size={30} /></span>
              <span>Modo</span>
              <strong>Asistente</strong>
            </div>

            <div className="home-status-card accent-cyan">
              <span className="status-icon"><Keyboard size={30} /></span>
              <span>Entrada</span>
              <strong>Texto / Voz</strong>
            </div>
          </div>
        )}
      </div>

      {hasResponse && (
        <div className="jarvis-mini-chat">
          <div className="mini-chat-title">
            <span>Conversación activa</span>
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
