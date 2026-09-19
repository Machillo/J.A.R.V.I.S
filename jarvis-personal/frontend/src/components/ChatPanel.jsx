import { deviceLanguage, tx } from "../lib/locale";

export default function ChatPanel({ response }) {
  if (!response) return null;

  const language = deviceLanguage();
  const copy = (es, en) => tx(es, en, language);
  const message = response.message || copy("Respuesta recibida.", "Response received.");
  const isPending = response.pending || response.status === "PENDING";

  return (
    <section className={`jarvis-chat-panel ${isPending ? "pending" : ""}`}>
      <div className="panel-title">
        <div>
          <h3>{copy("CONSOLA DE J.A.R.V.I.S.", "J.A.R.V.I.S. CONSOLE")}</h3>
          <p>{isPending ? copy("Esperando datos", "Waiting for data") : copy("Respuesta generada", "Response generated")}</p>
        </div>
      </div>

      <div className="jarvis-message">
        <span className="message-label">JARVIS</span>
        <p>{message}</p>
      </div>
    </section>
  );
}
