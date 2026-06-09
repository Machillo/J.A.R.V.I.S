import { useEffect, useState } from "react";
import {
  getJarvisUsageAdmin,
  getJarvisUsageToday,
  getJarvisPremiumStatus,
  getJarvisPremiumGuides,
  createJarvisPremiumInitialStrategy,
  getMe,
  getSportsPreferences,
  getUpcomingCalendarEvents,
  getNotificationStatus,
  sendTestNotification,
  updateSportsPreferences,
} from "../services/jarvisApi";
import { enableJarvisPushNotifications, isPushSupported } from "../pushNotifications";

const splitTeams = (value) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const JARVIS_THEMES = [
  { id: "classic", label: "Jarvis Tech", description: "Cian y morado sobre negro profundo.", swatches: ["#29e6ff", "#a855f7"] },
  { id: "elegant", label: "Elegante", description: "Carbón, marfil y dorado suave.", swatches: ["#e8dcc2", "#c7a968"] },
  { id: "finance", label: "Finanzas", description: "Azul petróleo y verde dinero.", swatches: ["#2dd4bf", "#74f2a7"] },
  { id: "minimal", label: "Minimal", description: "Gris oscuro, blanco y celeste limpio.", swatches: ["#e5eef4", "#8ecae6"] },
  { id: "premium", label: "Premium", description: "Negro, cobre y ámbar.", swatches: ["#d29b6c", "#f0c36a"] },
  { id: "ironman", label: "Iron Man", description: "Rojo profundo con dorado reactor.", swatches: ["#ef4444", "#f7c948"] },
];

export default function Settings({ status }) {
  const [me, setMe] = useState(null);
  const [usage, setUsage] = useState(null);
  const [premiumStatus, setPremiumStatus] = useState(null);
  const [premiumGuides, setPremiumGuides] = useState([]);
  const [premiumMessage, setPremiumMessage] = useState("");
  const [adminUsage, setAdminUsage] = useState(null);
  const [sports, setSports] = useState(null);
  const [teamsText, setTeamsText] = useState("");
  const [calendar, setCalendar] = useState([]);
  const [notificationStatus, setNotificationStatus] = useState("default");
  const [pushInfo, setPushInfo] = useState(null);
  const [pushMessage, setPushMessage] = useState("");
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem("jarvis-theme") || "classic";
    const legacyMap = { emerald: "finance", violet: "classic", amber: "premium", ice: "minimal" };
    return legacyMap[saved] || saved;
  });
  const [showThemePicker, setShowThemePicker] = useState(false);

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
        try {
          const [premiumData, guideData] = await Promise.all([
            getJarvisPremiumStatus(),
            getJarvisPremiumGuides(),
          ]);
          setPremiumStatus(premiumData);
          setPremiumGuides(guideData?.items || []);
        } catch (error) {
          console.warn("No pude cargar ChatGPT Premium", error);
        }
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



  const handleCreatePremiumStrategy = async () => {
    setPremiumMessage("Analizando finanzas con ChatGPT...");
    try {
      const result = await createJarvisPremiumInitialStrategy();
      setPremiumMessage(result?.status === "OK" ? "Señor, estrategia premium creada y guardada." : result?.message || "No pude crear la estrategia.");
      const [premiumData, guideData] = await Promise.all([getJarvisPremiumStatus(), getJarvisPremiumGuides()]);
      setPremiumStatus(premiumData);
      setPremiumGuides(guideData?.items || []);
    } catch (error) {
      setPremiumMessage(error.message);
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

      <div className="jarvis-panel settings-card theme-card collapsed-theme-card">
        <div>
          <h2>Estilo visual</h2>
          <p>Actual: <strong>{JARVIS_THEMES.find((item) => item.id === theme)?.label || "Jarvis Tech"}</strong></p>
        </div>

        <button
          className="jarvis-action-button theme-toggle-button"
          type="button"
          onClick={() => setShowThemePicker((value) => !value)}
        >
          Cambiar estilo
        </button>

        {showThemePicker && (
          <div className="theme-picker compact-theme-picker">
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
                <small>{item.description}</small>
              </button>
            ))}
          </div>
        )}
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


      {isOwner && (
        <div className="jarvis-panel settings-card premium-ai-card">
          <h2>ChatGPT Premium</h2>
          <p><strong>Estado:</strong> {premiumStatus?.configured ? "Conectado" : "Falta OPENAI_API_KEY"}</p>
          <p><strong>Modelo:</strong> {premiumStatus?.model || "—"}</p>
          <p><strong>Presupuesto mensual:</strong> ${Number(premiumStatus?.budget_usd || 10).toFixed(2)}</p>
          <p><strong>Usado:</strong> ${Number(premiumStatus?.used_usd || 0).toFixed(4)} · {Number(premiumStatus?.percent_used || 0).toFixed(1)}%</p>
          <div className="usage-bar premium-budget-bar">
            <span style={{ width: `${Math.min(premiumStatus?.percent_used || 0, 100)}%` }} />
          </div>
          <button className="jarvis-action-button" type="button" onClick={handleCreatePremiumStrategy} disabled={!premiumStatus?.configured}>
            Crear análisis financiero premium
          </button>
          <small>ChatGPT solo se usa para owner, con límite mensual. El backend sigue haciendo los cálculos exactos.</small>
          {premiumMessage && <small className="email-sync-status">{premiumMessage}</small>}
          {premiumGuides.length > 0 && (
            <div className="settings-list premium-guides-list">
              {premiumGuides.slice(0, 2).map((guide) => (
                <div key={guide.id}>
                  <strong>{guide.title || guide.guide_type}</strong>
                  <span>{String(guide.content || "").slice(0, 180)}...</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

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
