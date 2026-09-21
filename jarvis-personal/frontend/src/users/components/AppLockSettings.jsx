import { useEffect, useState } from "react";
import { Fingerprint, LockKeyhole, ShieldCheck } from "lucide-react";
import {
  APP_LOCK_TIMEOUTS,
  appLockErrorMessage,
  authenticateAppLock,
  biometryLabel,
  getAppLockConfig,
  getBiometryStatus,
  isNativeAppLockSupported,
  requestAppLock,
  saveAppLockConfig,
} from "../../lib/appLock";
import { tx } from "../../lib/locale";

const timeoutLabels = {
  0: ["Inmediatamente", "Immediately"],
  60000: ["Después de 1 minuto", "After 1 minute"],
  300000: ["Después de 5 minutos", "After 5 minutes"],
  900000: ["Después de 15 minutos", "After 15 minutes"],
  3600000: ["Después de 1 hora", "After 1 hour"],
};

export default function AppLockSettings({ userId }) {
  const [config, setConfig] = useState(() => getAppLockConfig(userId));
  const [status, setStatus] = useState(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setConfig(getAppLockConfig(userId));
    if (!isNativeAppLockSupported()) return;
    getBiometryStatus().then(setStatus).catch(() => setStatus({ isAvailable: false, deviceIsSecure: false }));
  }, [userId]);

  const toggle = async () => {
    if (working) return;
    if (!config.enabled && !status?.isAvailable) {
      setMessage(tx("Configurá primero la huella o Face ID en el teléfono.", "Set up fingerprint or Face ID on your phone first."));
      return;
    }
    setWorking(true);
    setMessage("");
    try {
      if (!config.enabled) await authenticateAppLock();
      const next = saveAppLockConfig(userId, { ...config, enabled: !config.enabled });
      setConfig(next);
      setMessage(next.enabled ? tx("Protección activada.", "Protection enabled.") : tx("Protección desactivada.", "Protection disabled."));
    } catch (error) {
      setMessage(appLockErrorMessage(error));
    } finally {
      setWorking(false);
    }
  };

  const changeTimeout = (event) => {
    const next = saveAppLockConfig(userId, { ...config, timeoutMs: Number(event.target.value) });
    setConfig(next);
    setMessage(tx("Tiempo de bloqueo actualizado.", "Lock timing updated."));
  };

  if (!isNativeAppLockSupported()) {
    return <article className="app-lock-settings account-card app-lock-settings--web"><LockKeyhole size={22}/><div><strong>{tx("Bloqueo de FINVA", "FINVA app lock")}</strong><small>{tx("Disponible en la aplicación para Android y iPhone.", "Available in the Android and iPhone app.")}</small></div></article>;
  }

  const label = biometryLabel(status?.biometryType);
  return (
    <article className="app-lock-settings">
      <header>
        <span><ShieldCheck size={22}/></span>
        <div><strong>{tx("Bloqueo de FINVA", "FINVA app lock")}</strong><small>{tx(`Protegé la app con ${label} o el código del teléfono.`, `Protect the app with ${label} or your device passcode.`)}</small></div>
        <button className={`app-lock-toggle ${config.enabled ? "is-on" : ""}`} type="button" role="switch" aria-checked={config.enabled} disabled={working || status === null} onClick={toggle}><i /></button>
      </header>
      {config.enabled && <label className="app-lock-timeout"><span>{tx("Bloquear al salir", "Lock after leaving")}</span><select value={config.timeoutMs} onChange={changeTimeout}>{APP_LOCK_TIMEOUTS.map((timeout) => <option value={timeout} key={timeout}>{tx(...timeoutLabels[timeout])}</option>)}</select></label>}
      {config.enabled && <button className="app-lock-now" type="button" onClick={() => requestAppLock(userId)}><Fingerprint size={18}/>{tx("Bloquear ahora", "Lock now")}</button>}
      {message && <small className="app-lock-message" role="status">{message}</small>}
    </article>
  );
}
