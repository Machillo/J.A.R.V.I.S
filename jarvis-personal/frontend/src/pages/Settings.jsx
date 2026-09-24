import { useEffect, useState } from "react";
import { ArrowLeft, Bell, CalendarDays, RadioTower, Trophy } from "lucide-react";
import {
  getMe,
  getSportsPreferences,
  getUpcomingCalendarEvents,
  getNotificationStatus,
  sendTestNotification,
  updateSportsPreferences,
  linkOwnerToUsers,
  getDeploymentMonitor,
} from "../services/jarvisApi";
import { enableJarvisPushNotifications, isPushSupported } from "../pushNotifications";
import { JarvisGlassCard, JarvisMenuRow, JarvisScreen, JarvisStatusPill } from "../products/jarvis/components/JarvisScreen";

const splitTeams = (value) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);



export default function Settings({ status }) {
  const [section, setSection] = useState("general");
  const [me, setMe] = useState(null);
  const [sports, setSports] = useState(null);
  const [teamsText, setTeamsText] = useState("");
  const [calendar, setCalendar] = useState([]);
  const [notificationStatus, setNotificationStatus] = useState("default");
  const [pushInfo, setPushInfo] = useState(null);
  const [pushMessage, setPushMessage] = useState("");
  const [ownerBridgeMessage, setOwnerBridgeMessage] = useState("");
  const [ownerBridgeBusy, setOwnerBridgeBusy] = useState(false);
  const [deployments, setDeployments] = useState(null);

  const isOwner = me?.role === "owner";

  const load = async () => {
    try {
      const [meData, sportsData, calendarData] = await Promise.all([
        getMe(),
        getSportsPreferences(),
        getUpcomingCalendarEvents(45),
      ]);

      setMe(meData);
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

      try {
        setDeployments(await getDeploymentMonitor());
      } catch (error) {
        console.warn("No pude cargar el monitor de despliegues", error);
      }

    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    load();
  }, []);


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



  const handleLinkOwnerBridge = async () => {
    setOwnerBridgeBusy(true);
    setOwnerBridgeMessage("Verificando ambas identidades...");
    try {
      const result = await linkOwnerToUsers();
      setOwnerBridgeMessage(result?.verified ? "Tu espacio interno quedó vinculado con tu cuenta Owner de DINCR." : "No se pudo verificar el vínculo.");
    } catch (error) {
      setOwnerBridgeMessage(error.message);
    } finally {
      setOwnerBridgeBusy(false);
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

  const back = section === "general" ? null : <button className="jarvis-circle-button" type="button" onClick={() => setSection("general")} aria-label="Volver"><ArrowLeft size={19} /></button>;

  if (section === "notifications") return <JarvisScreen eyebrow="Configuración" title="Notificaciones" subtitle="Web Push, calendario y deportes" actions={back} className="settings-screen settings-notifications">
    <JarvisGlassCard className="settings-detail-card"><JarvisStatusPill tone={pushInfo?.subscriptions ? "success" : "warning"}>{pushInfo?.subscriptions ? "WEB PUSH ACTIVO" : "WEB PUSH INACTIVO"}</JarvisStatusPill><h3>Este dispositivo</h3><p>Permiso {notificationStatus} · {pushInfo?.vapid_ready ? "VAPID listo" : "VAPID pendiente"}</p><p>{pushInfo?.subscriptions ?? 0} dispositivos registrados</p><b>{pushInfo?.pending_jobs ?? 0} alertas pendientes</b><div className="settings-card-actions"><button className="jarvis-primary-button" type="button" onClick={handleEnableNotifications} disabled={!isPushSupported()}>Activar</button><button className="jarvis-primary-button" type="button" onClick={handleTestNotification} disabled={!pushInfo?.subscriptions}>Enviar prueba</button></div>{pushMessage && <small>{pushMessage}</small>}</JarvisGlassCard>
    <JarvisGlassCard className="settings-detail-card"><span className="settings-card-label">PRÓXIMOS EVENTOS</span><div className="settings-compact-list">{calendar.length ? calendar.slice(0, 6).map((event) => <div key={event.id}><b>{event.event_date}</b><span>{event.title}</span></div>) : <p>No hay compromisos próximos.</p>}</div></JarvisGlassCard>
    <JarvisGlassCard className="settings-detail-card"><span className="settings-card-label">PREFERENCIAS DEPORTIVAS</span><ToggleRow label="F1" detail="Prácticas · Qualy · Carrera" checked={Boolean(sports?.f1)} onChange={(checked) => setSports((current) => ({ ...(current || {}), f1: checked }))} /><ToggleRow label="UFC" detail="Cartelera principal" checked={Boolean(sports?.ufc)} onChange={(checked) => setSports((current) => ({ ...(current || {}), ufc: checked }))} /><label className="settings-team-field"><span>Fútbol</span><input value={teamsText} onChange={(event) => setTeamsText(event.target.value)} placeholder="Real Madrid, Costa Rica" /></label><button className="jarvis-primary-button" type="button" onClick={handleSaveSports}>Guardar preferencias</button></JarvisGlassCard>
  </JarvisScreen>;

  if (section === "owner") return <JarvisScreen eyebrow="Owner" title="Centro Owner" subtitle="Identidad privada y operación" actions={back} className="settings-screen settings-owner">
    <JarvisGlassCard className="settings-detail-card"><span className="settings-card-label">IDENTIDAD DINCR</span><h3>Personal ↔ Cuenta pública</h3><p>Vinculación segura por UUID verificado</p><JarvisStatusPill tone="success">CONECTADA</JarvisStatusPill><button className="jarvis-primary-button" type="button" onClick={handleLinkOwnerBridge} disabled={ownerBridgeBusy}>{ownerBridgeBusy ? "Verificando..." : "Administrar vínculo"}</button>{ownerBridgeMessage && <small>{ownerBridgeMessage}</small>}</JarvisGlassCard>
    <h3 className="settings-section-title">Monitor de despliegues</h3>{Object.entries(deployments?.latest || {}).map(([provider, item]) => <JarvisGlassCard className="deployment-card" key={provider}><span>{provider.toUpperCase()}</span><strong>{item.service_name || provider}</strong><small>Commit {item.commit_sha?.slice(0, 7) || "—"}</small><JarvisStatusPill tone={item.status === "success" ? "success" : item.status === "failure" ? "danger" : "warning"}>{item.status === "success" ? "Correcto" : item.status}</JarvisStatusPill></JarvisGlassCard>)}
    <JarvisGlassCard className="settings-detail-card"><span className="settings-card-label">EVENTOS RECIENTES</span><div className="settings-compact-list">{(deployments?.events || []).slice(0, 5).map((item) => <div key={item.id}><b>{item.provider}</b><span>{item.summary || item.event_type}</span>{item.log_url && <a href={item.log_url} target="_blank" rel="noreferrer">Abrir log</a>}</div>)}</div></JarvisGlassCard>
  </JarvisScreen>;

  return <JarvisScreen eyebrow="Configuración" title="Configuración" subtitle="Cuenta y preferencias" className="settings-screen settings-general">
    <JarvisGlassCard className="settings-user-card"><span>USUARIO ACTUAL</span><strong>{me?.email || "—"}</strong><small>{me?.role || "—"}</small><JarvisStatusPill tone="success">{String(me?.status || "activo").toUpperCase()}</JarvisStatusPill></JarvisGlassCard>
    <div className="settings-menu"><h3>Preferencias</h3><JarvisMenuRow icon={Bell} title="Notificaciones" detail="Web Push, calendario y deportes" onClick={() => setSection("notifications")} />{isOwner && <JarvisMenuRow icon={RadioTower} title="Centro Owner" detail="Identidad y despliegues" onClick={() => setSection("owner")} />}<JarvisMenuRow icon={CalendarDays} title="Calendario" detail={`${calendar.length} próximos compromisos`} onClick={() => setSection("notifications")} /><JarvisMenuRow icon={Trophy} title="Deportes" detail="F1 · UFC · Fútbol" onClick={() => setSection("notifications")} /></div>
    {status?.config && <small className="settings-system-note">Sistema DINCR sincronizado</small>}
  </JarvisScreen>;
}

function ToggleRow({ label, detail, checked, onChange }) {
  return <label className="settings-toggle-row"><strong>{label}</strong><span>{detail}</span><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /></label>;
}
