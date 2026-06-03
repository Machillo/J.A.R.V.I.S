import { Brain, Sparkles } from "lucide-react";

function formatJarvisResponse(data) {
  if (!data) return null;

  if (data.message) {
    return data.message;
  }

  return "Señor, análisis completado.";
}

export default function Dashboard({ jarvisResponse }) {
  const responseText = formatJarvisResponse(jarvisResponse);
  const hasResponse = Boolean(responseText);

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
            <div className="home-status-card">
              <span>Sistema</span>
              <strong>Activo</strong>
            </div>

            <div className="home-status-card">
              <span>Modo</span>
              <strong>Asistente</strong>
            </div>

            <div className="home-status-card">
              <span>Entrada</span>
              <strong>Texto / Voz</strong>
            </div>
          </div>
        )}
      </div>

      {hasResponse && (
        <div className="jarvis-chat-panel">
          <div className="panel-title">
            <div>
              <h3>CONSOLA DE J.A.R.V.I.S.</h3>
              <p>Respuesta generada</p>
            </div>

            <Sparkles size={20} />
          </div>

          <div className="jarvis-message">
            <span className="message-label">JARVIS</span>
            <p>{responseText}</p>
          </div>
        </div>
      )}
    </section>
  );
}