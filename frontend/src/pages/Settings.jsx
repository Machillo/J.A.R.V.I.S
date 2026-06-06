import { useEffect, useState } from "react";
import {
  getJarvisUsageAdmin,
  getJarvisUsageToday,
  getMe,
  getSportsPreferences,
  getUpcomingCalendarEvents,
  getEmailMonitorCandidates,
  getEmailMonitorStatus,
  getNotificationStatus,
  sendTestNotification,
  syncEmailMonitorGmail,
  updateSportsPreferences,
} from "../services/jarvisApi";
import { enableJarvisPushNotifications, isPushSupported } from "../pushNotifications";

const splitTeams = (value) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const JARVIS_THEMES = [
  { id: "classic", label: "Cian / Morado", swatches: ["#29e6ff", "#c155ff"] },
  { id: "emerald", label: "Verde / Cian", swatches: ["#51ff9b", "#29e6ff"] },
  { id: "violet", label: "Violeta / Rosa", swatches: ["#b25cff", "#ff4fd8"] },
  { id: "amber", label: "Ámbar / Cian", swatches: ["#ffcc66", "#29e6ff"] },
  { id: "ice", label: "Hielo / Azul", swatches: ["#9ff8ff", "#5b7cff"] },
];

export default function Settings({ status }) {
  const [me, setMe] = useState(null);
  const [usage, setUsage] = useState(null);
  const [adminUsage, setAdminUsage] = useState(null);
  const [sports, setSports] = useState(null);
  const [teamsText, setTeamsText] = useState("");
  const [calendar, setCalendar] = useState([]);
  const [notificationStatus, setNotificationStatus] = useState("default");
  const [pushInfo, setPushInfo] = useState(null);
  const [pushMessage, setPushMessage] = useState("");
  const [emailMonitor, setEmailMonitor] = useState(null);
  const [emailCandidates, setEmailCandidates] = useState([]);
  const [emailSyncStatus, setEmailSyncStatus] = useState("");
  const [theme, setTheme] = useState(() => localStorage.getItem("jarvis-theme") || "classic");

  const isAdmin = me?.role === "owner" || me?.role === "admin";
  const isOwner = me?.role === "owner";

  const load = async () => {
    try {
      const [meData, usageData, sportsData, calendarData] = await Promise.all([
        getMe(),
        getJarvisUsageToday(),
        getSportsPreferences(),
        getUpcomingCalendarEvents(45),
      ]);

      setMe(meData);
      setUsage(usageData);
      setSports(sportsData);
      setTeamsText((sportsData?.football?.teams || []).join(", "));
      setCalendar(calendarData?.events || []);

      if (typeof Notification !== "undefined") {
        setNotificationStatus(Notification.permission);
      }

      try {
        const notificationData = await getNotificationStatus();
        setPushInfo(notificationData);
      } catch (error) {
        console.warn("No pude cargar estado Web Push", error);
      }

      if (meData?.role === "owner" || meData?.role === "admin") {
        const adminData = await getJarvisUsageAdmin();
        setAdminUsage(adminData);
      }

      if (meData?.role === "owner") {
        const [emailStatus, pendingEmails] = await Promise.all([
          getEmailMonitorStatus(),
          getEmailMonitorCandidates("pending", 5),
        ]);
        setEmailMonitor(emailStatus);
        setEmailCandidates(pendingEmails?.items || []);
      }
    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("jarvis-theme", theme);
    window.dispatchEvent(new Event("jarvis-theme-change"));
  }, [theme]);

  const handleSaveSports = async () => {
    const payload = {
      f1: Boolean(sports?.f1),
      ufc: Boolean(sports?.ufc),
      notification_style: sports?.notification_style || "Señor",
      football: {
        teams: splitTeams(teamsText),
        competitions: sports?.football?.competitions || ["Champions League", "Mundial de Clubes", "Mundial"],
      },
    };

    const result = await updateSportsPreferences(payload);
    setSports(result.value || payload);
  };


  const handleEmailSync = async () => {
    setEmailSyncStatus("Escaneando solo correos del mes actual...");
    try {
      const result = await syncEmailMonitorGmail({
        max_results: 25,
        auto_commit: true,
        current_month_only: true,
      });
      const summary = result?.summary || {};
      setEmailSyncStatus(
        result?.message ||
          `Encontrados: ${result?.found || 0} · Guardados: ${summary.auto_saved || 0} · Pendientes: ${summary.pending || 0}`
      );
      const [emailStatus, pendingEmails] = await Promise.all([
        getEmailMonitorStatus(),
        getEmailMonitorCandidates("pending", 10),
      ]);
      setEmailMonitor(emailStatus);
      setEmailCandidates(pendingEmails?.items || []);
    } catch (error) {
      setEmailSyncStatus(error.message);
    }
  };

  const handleEnableNotifications = async () => {
    setPushMessage("Activando Web Push...");
    try {
      const result = await enableJarvisPushNotifications();
      setNotificationStatus(result.permission);
      setPushInfo(result.status);
      setPushMessage(result.test?.message || "Señor, notificaciones activadas en este dispositivo.");
    } catch (error) {
      setPushMessage(error.message);
    }
  };

  const handleTestNotification = async () => {
    setPushMessage("Enviando prueba...");
    try {
      const result = await sendTestNotification();
      setPushMessage(result?.message || "Señor, prueba enviada.");
      const notificationData = await getNotificationStatus();
      setPushInfo(notificationData);
    } catch (error) {
      setPushMessage(error.message);
    }
  };

  return (
    <section className="page settings-page">
      <h1>Configuración</h1>
      <p className="subtitle">Perfil, permisos, IA, notificaciones y preferencias personales.</p>

      <div className="jarvis-panel settings-card theme-card">
        <div>
          <h2>Estilo visual</h2>
          <p>Elegí una combinación neón. Queda guardada en este dispositivo.</p>
        </div>
        <div className="theme-picker">
          {JARVIS_THEMES.map((item) => (
            <button
              key={item.id}
              className={`theme-option ${theme === item.id ? "active" : ""}`}
              onClick={() => setTheme(item.id)}
              aria-label={`Usar tema ${item.label}`}
              type="button"
            >
              <span style={{ background: item.swatches[0] }} />
              <span style={{ background: item.swatches[1] }} />
              <em>{item.label}</em>
            </button>
          ))}
        </div>
      </div>

      <div className="settings-grid">
        <div className="jarvis-panel settings-card">
          <h2>Usuario actual</h2>
          <p><strong>Email:</strong> {me?.email || "—"}</p>
          <p><strong>Rol:</strong> {me?.role || "—"}</p>
          <p><strong>Estado:</strong> {me?.status || "—"}</p>
          {isOwner && <p className="owner-badge">Acceso owner: internet + administración completa</p>}
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

      <div className="settings-grid">
        <div className="jarvis-panel settings-card">
          <h2>Notificaciones reales</h2>
          <p>Permiso navegador: <strong>{notificationStatus}</strong></p>
          <p>Web Push: <strong>{pushInfo?.vapid_ready ? "Listo" : "Faltan llaves VAPID"}</strong></p>
          <p>Dispositivos registrados: <strong>{pushInfo?.subscriptions ?? 0}</strong></p>
          <p>Alertas pendientes: <strong>{pushInfo?.pending_jobs ?? 0}</strong></p>
          <button className="jarvis-action-button" onClick={handleEnableNotifications} disabled={!isPushSupported()}>
            Activar Web Push en este iPhone
          </button>
          <button className="jarvis-action-button secondary" onClick={handleTestNotification} disabled={!pushInfo?.subscriptions}>
            Enviar prueba
          </button>
          <small>
            En iPhone funciona cuando JARVIS está agregado a pantalla de inicio como PWA y las notificaciones están permitidas.
          </small>
          {pushMessage && <small className="email-sync-status">{pushMessage}</small>}
        </div>

        <div className="jarvis-panel settings-card">
          <h2>Calendario próximo</h2>
          {calendar.length === 0 ? (
            <p>No hay compromisos próximos.</p>
          ) : (
            <div className="settings-list">
              {calendar.slice(0, 6).map((event) => (
                <div key={event.id}>
                  <strong>{event.event_date}</strong>
                  <span>{event.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>


      {isOwner && (
        <div className="settings-grid">
          <div className="jarvis-panel settings-card">
            <h2>Correos financieros 24/7</h2>
            <p><strong>Gmail listo:</strong> {emailMonitor?.gmail_ready ? "Sí" : "Faltan llaves Gmail"}</p>
            <p><strong>Último escaneo:</strong> {emailMonitor?.settings?.last_scan_at ? new Date(emailMonitor.settings.last_scan_at).toLocaleString("es-CR") : "Nunca"}</p>
            <p><strong>Pendientes:</strong> {emailMonitor?.totals?.pending || 0}</p>
            <p><strong>Auto guardados:</strong> {emailMonitor?.totals?.auto_saved || 0}</p>
            <button className="jarvis-action-button" onClick={handleEmailSync} disabled={!emailMonitor?.gmail_ready}>
              Escanear correos del mes actual
            </button>
            <small>Busca BAC, Credomatic, Banco Popular y MultiMoney solo desde el primer día del mes actual.</small>
            {emailSyncStatus && <small className="email-sync-status">{emailSyncStatus}</small>}
            {!emailMonitor?.gmail_ready && (
              <small>
                Para lectura real agregá GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET y GMAIL_REFRESH_TOKEN en Render.
              </small>
            )}
          </div>

          <div className="jarvis-panel settings-card">
            <h2>Correos por confirmar</h2>
            {emailCandidates.length === 0 ? (
              <p>No hay movimientos dudosos pendientes.</p>
            ) : (
              <div className="settings-list">
                {emailCandidates.map((item) => (
                  <div key={item.id}>
                    <strong>{item.transaction_date} · ₡{Number(item.amount || 0).toLocaleString("es-CR")}</strong>
                    <span>{item.description}</span>
                    <small>{item.category} · {item.review_reason}</small>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="jarvis-panel settings-card">
        <h2>Preferencias deportivas</h2>
        <label className="settings-check">
          <input
            type="checkbox"
            checked={Boolean(sports?.f1)}
            onChange={(event) => setSports((current) => ({ ...(current || {}), f1: event.target.checked }))}
          />
          Fórmula 1: prácticas, clasificación, sprint y carrera
        </label>
        <label className="settings-check">
          <input
            type="checkbox"
            checked={Boolean(sports?.ufc)}
            onChange={(event) => setSports((current) => ({ ...(current || {}), ufc: event.target.checked }))}
          />
          UFC: peleas y carteleras importantes
        </label>
        <label className="settings-label">
          Equipos favoritos
          <textarea
            value={teamsText}
            onChange={(event) => setTeamsText(event.target.value)}
            placeholder="Real Madrid, Saprissa, Manchester City..."
          />
        </label>
        <button className="jarvis-action-button" onClick={handleSaveSports}>
          Guardar preferencias
        </button>
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
