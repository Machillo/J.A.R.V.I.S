import StatusCard from "../components/StatusCard";

export default function Dashboard({ status, jarvisResponse }) {
  return (
    <section className="page">
      <h1>Dashboard</h1>
      <p className="subtitle">Estado general de JARVIS</p>

      <div className="cards-grid">
        <StatusCard
          title="Usuario"
          value={status?.user?.name || "Sin usuario"}
          subtitle={status?.user?.country || "Sin país"}
        />

        <StatusCard
          title="Hora"
          value={status?.time?.time || "--:--"}
          subtitle={status?.time?.date || "Fecha no disponible"}
        />

        <StatusCard
          title="Zona horaria"
          value={status?.config?.timezone || "Sin zona"}
          subtitle="Sistema activo"
        />
      </div>

      <div className="jarvis-panel">
        <h2>Respuesta de Jarvis</h2>
        <pre>
          {jarvisResponse
            ? JSON.stringify(jarvisResponse, null, 2)
            : "Esperando instrucción..."}
        </pre>
      </div>
    </section>
  );
}