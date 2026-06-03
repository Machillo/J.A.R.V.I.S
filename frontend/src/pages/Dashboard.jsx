import { Brain, Mic, Sparkles } from "lucide-react";

function formatJarvisResponse(data) {
  if (!data) {
    return "Señor, estoy listo para asistirle.";
  }

  if (data.response?.reason) {
    return `Señor, considero que la mejor estrategia es "${data.response.name}". ${data.response.reason}`;
  }

  if (data.message) {
    return data.message;
  }

  if (data.response?.message) {
    return data.response.message;
  }

  return "Señor, análisis completado.";
}

export default function Dashboard({ jarvisResponse }) {
  return (
    <section className="jarvis-home">
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

      <div className="jarvis-home-panel">
        <div className="panel-title">
          <div>
            <h3>CONSOLA DE JARVIS</h3>
            <p>Última interacción</p>
          </div>

          <Sparkles size={20} />
        </div>

        <div className="jarvis-response">
          {formatJarvisResponse(jarvisResponse)}
        </div>
      </div>

      <div className="home-hint">
        <Mic size={18} />
        <span>Usa el comando inferior para hablar conmigo.</span>
      </div>
    </section>
  );
}