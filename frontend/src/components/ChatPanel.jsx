export default function ChatPanel({ response }) {
  if (!response) return null;

  const message = response.message || "Respuesta recibida.";
  const isPending = response.pending || response.status === "PENDING";

  return (
    <section className={`jarvis-chat-panel ${isPending ? "pending" : ""}`}>
      <div className="panel-title">
        <div>
          <h3>CONSOLA DE J.A.R.V.I.S.</h3>
          <p>{isPending ? "Esperando datos" : "Respuesta generada"}</p>
        </div>
      </div>

      <div className="jarvis-message">
        <span className="message-label">JARVIS</span>
        <p>{message}</p>
      </div>
    </section>
  );
}
