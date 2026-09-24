import { useEffect, useState } from "react";
import { Fingerprint, LockKeyhole, ShieldCheck } from "lucide-react";
import {
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

  if (!isNativeAppLockSupported()) {
    return <article className="app-lock-settings account-card app-lock-settings--web"><LockKeyhole size={22}/><div><strong>{tx("Bloqueo de DINCR", "DINCR app lock")}</strong><small>{tx("Disponible en la aplicación para Android y iPhone.", "Available in the Android and iPhone app.")}</small></div></article>;
  }

  const label = biometryLabel(status?.biometryType);
  return (
    <article className="app-lock-settings">
      <header>
        <span><ShieldCheck size={22}/></span>
        <div><strong>{tx("Bloqueo de DINCR", "DINCR app lock")}</strong><small>{tx(`Protegé la app con ${label} o el código del teléfono.`, `Protect the app with ${label} or your device passcode.`)}</small></div>
        <button className={`app-lock-toggle ${config.enabled ? "is-on" : ""}`} type="button" role="switch" aria-checked={config.enabled} aria-label={tx("Bloqueo de DINCR", "DINCR app lock")} disabled={working || status === null} onClick={toggle}><i /></button>
      </header>
      {config.enabled && <div className="app-lock-timeout"><span>{tx("Bloqueo automático", "Automatic lock")}</span><strong>{tx("Después de 5 minutos fuera de DINCR", "After 5 minutes away from DINCR")}</strong></div>}
      {config.enabled && <button className="app-lock-now" type="button" onClick={() => requestAppLock(userId)}><Fingerprint size={18}/>{tx("Bloquear ahora", "Lock now")}</button>}
      {message && <small className="app-lock-message" role="status">{message}</small>}
    </article>
  );
}
