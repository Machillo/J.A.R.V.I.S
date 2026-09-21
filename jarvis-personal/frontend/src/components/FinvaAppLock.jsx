import { useCallback, useEffect, useRef, useState } from "react";
import { App as CapacitorApp } from "@capacitor/app";
import { Fingerprint, LogOut, ShieldCheck } from "lucide-react";
import {
  APP_LOCK_CHANGED_EVENT,
  APP_LOCK_REQUESTED_EVENT,
  appLockErrorMessage,
  authenticateAppLock,
  getAppLockConfig,
  isNativeAppLockSupported,
  shouldLockAfterInactivity,
} from "../lib/appLock";
import { tx } from "../lib/locale";
import "./FinvaAppLock.css";

export default function FinvaAppLock({ userId, onLogout, children }) {
  const [config, setConfig] = useState(() => getAppLockConfig(userId));
  const [locked, setLocked] = useState(() => isNativeAppLockSupported() && getAppLockConfig(userId).enabled);
  const [appActive, setAppActive] = useState(true);
  const [message, setMessage] = useState("");
  const inactiveAt = useRef(null);
  const authenticating = useRef(false);

  useEffect(() => {
    const next = getAppLockConfig(userId);
    setConfig(next);
    setLocked(isNativeAppLockSupported() && next.enabled);
    setMessage("");
  }, [userId]);

  const unlock = useCallback(async () => {
    if (authenticating.current) return;
    authenticating.current = true;
    setMessage("");
    try {
      await authenticateAppLock();
      inactiveAt.current = null;
      setLocked(false);
    } catch (error) {
      setMessage(appLockErrorMessage(error));
    } finally {
      authenticating.current = false;
    }
  }, []);

  useEffect(() => {
    if (!appActive || !locked || !config.enabled || !isNativeAppLockSupported()) return;
    unlock();
  }, [appActive, config.enabled, locked, unlock]);

  useEffect(() => {
    let nativeListener;
    const onStateChange = ({ isActive }) => {
      if (!config.enabled || authenticating.current) return;
      if (!isActive) {
        setAppActive(false);
        inactiveAt.current = Date.now();
        if (config.timeoutMs === 0) setLocked(true);
        return;
      }
      setAppActive(true);
      if (inactiveAt.current !== null && shouldLockAfterInactivity(config.timeoutMs, Date.now() - inactiveAt.current)) {
        setLocked(true);
      }
      inactiveAt.current = null;
    };
    CapacitorApp.addListener("appStateChange", onStateChange).then((listener) => { nativeListener = listener; });
    return () => nativeListener?.remove();
  }, [config.enabled, config.timeoutMs]);

  useEffect(() => {
    const changed = (event) => {
      if (event.detail?.userId !== userId) return;
      setConfig(event.detail.config);
      if (!event.detail.config.enabled) setLocked(false);
    };
    const requested = (event) => {
      if (event.detail?.userId === userId && config.enabled) setLocked(true);
    };
    window.addEventListener(APP_LOCK_CHANGED_EVENT, changed);
    window.addEventListener(APP_LOCK_REQUESTED_EVENT, requested);
    return () => {
      window.removeEventListener(APP_LOCK_CHANGED_EVENT, changed);
      window.removeEventListener(APP_LOCK_REQUESTED_EVENT, requested);
    };
  }, [config.enabled, userId]);

  if (!locked) return children;

  return (
    <main className="finva-app-lock" aria-live="polite">
      <section className="finva-app-lock-card">
        <div className="finva-app-lock-mark"><ShieldCheck size={34} /></div>
        <p>FINVA · {tx("SEGURIDAD", "SECURITY")}</p>
        <h1>{tx("FINVA está bloqueada", "FINVA is locked")}</h1>
        <span>{tx("Tus datos siguen privados. Confirmá que sos vos para continuar.", "Your data remains private. Confirm it’s you to continue.")}</span>
        {message && <div className="finva-app-lock-error" role="alert">{message}</div>}
        <button className="finva-app-unlock-button" type="button" onClick={unlock}>
          <Fingerprint size={21} /> {tx("Desbloquear", "Unlock")}
        </button>
        <button className="finva-app-logout-button" type="button" onClick={onLogout}>
          <LogOut size={18} /> {tx("Cerrar sesión", "Log out")}
        </button>
      </section>
    </main>
  );
}
