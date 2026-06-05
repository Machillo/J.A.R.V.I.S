import { useEffect, useState } from "react";
import { getJarvisUsageAdmin, getJarvisUsageToday, getMe } from "../services/jarvisApi";

export default function Settings({ status }) {
  const [me, setMe] = useState(null);
  const [usage, setUsage] = useState(null);
  const [adminUsage, setAdminUsage] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [meData, usageData] = await Promise.all([getMe(), getJarvisUsageToday()]);
        setMe(meData);
        setUsage(usageData);

        if (meData?.role === "owner" || meData?.role === "admin") {
          const adminData = await getJarvisUsageAdmin();
          setAdminUsage(adminData);
        }
      } catch (error) {
        console.error(error);
      }
    };

    load();
  }, []);

  return (
    <section className="page settings-page">
      <h1>Configuración</h1>
      <p className="subtitle">Perfil, permisos y consumo de IA.</p>

      <div className="settings-grid">
        <div className="jarvis-panel settings-card">
          <h2>Usuario actual</h2>
          <p><strong>Email:</strong> {me?.email || "—"}</p>
          <p><strong>Rol:</strong> {me?.role || "—"}</p>
          <p><strong>Estado:</strong> {me?.status || "—"}</p>
        </div>

        <div className="jarvis-panel settings-card">
          <h2>Consumo IA de hoy</h2>
          <p><strong>Tokens:</strong> {usage?.total_tokens?.toLocaleString("es-CR") || 0}</p>
          <p><strong>Límite:</strong> {usage?.daily_limit?.toLocaleString("es-CR") || "—"}</p>
          <p><strong>Disponible:</strong> {usage?.remaining_tokens?.toLocaleString("es-CR") || "—"}</p>
          <div className="usage-bar">
            <span style={{ width: `${Math.min(usage?.percent_used || 0, 100)}%` }} />
          </div>
        </div>
      </div>

      {adminUsage?.users?.length > 0 && (
        <div className="jarvis-panel admin-panel">
          <h2>Panel admin · consumo por usuario</h2>
          <div className="admin-usage-list">
            {adminUsage.users.map((user) => (
              <div key={user.user_id} className="admin-usage-row">
                <span>{user.email}</span>
                <small>{user.role}</small>
                <strong>{Number(user.total_tokens || 0).toLocaleString("es-CR")} / {Number(user.daily_limit || 0).toLocaleString("es-CR")}</strong>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="jarvis-panel settings-card">
        <h2>Config sistema</h2>
        <pre>{JSON.stringify(status?.config || {}, null, 2)}</pre>
      </div>
    </section>
  );
}
