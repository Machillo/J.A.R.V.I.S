export default function Settings({ status }) {
  return (
    <section className="page">
      <h1>Configuración</h1>
      <p className="subtitle">Configuración actual del sistema.</p>

      <div className="jarvis-panel">
        <pre>{JSON.stringify(status?.config || {}, null, 2)}</pre>
      </div>
    </section>
  );
}