import { useEffect, useState } from "react";
import { Fingerprint, KeyRound, ShieldCheck, TimerReset } from "lucide-react";
import {
  appLockErrorMessage,
  authenticateAppLock,
  biometryLabel,
  DEFAULT_APP_LOCK_TIMEOUT,
  getBiometryStatus,
  markAppLockOnboardingSeen,
  saveAppLockConfig,
} from "../lib/appLock";
import { tx } from "../lib/locale";

export default function DincrAppLockOnboarding({ userId, onFinish }) {
  const [status, setStatus] = useState(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    getBiometryStatus()
      .then(setStatus)
      .catch(() => setStatus({ isAvailable: false, deviceIsSecure: false }));
  }, []);

  const skip = () => {
    markAppLockOnboardingSeen(userId);
    onFinish();
  };

  const activate = async () => {
    if (working || !status?.isAvailable) return;
    setWorking(true);
    setMessage("");
    try {
      await authenticateAppLock();
      saveAppLockConfig(userId, { enabled: true, timeoutMs: DEFAULT_APP_LOCK_TIMEOUT });
      markAppLockOnboardingSeen(userId);
      onFinish();
    } catch (error) {
      setMessage(appLockErrorMessage(error));
    } finally {
      setWorking(false);
    }
  };

  const label = biometryLabel(status?.biometryType);
  return (
    <main className="dincr-app-lock dincr-app-lock--onboarding" aria-live="polite">
      <section className="dincr-app-lock-card dincr-app-lock-welcome">
        <div className="dincr-app-lock-mark"><KeyRound size={34} /></div>
        <p>DINCR · {tx("ACCESO SEGURO", "SECURE ACCESS")}</p>
        <h1>{tx(`Entrá con ${label}`, `Access with ${label}`)}</h1>
        <span>{tx("Después de iniciar con Google, DINCR puede usar la llave segura de este teléfono para proteger tus finanzas.", "After signing in with Google, DINCR can use this phone’s secure key to protect your finances.")}</span>
        <div className="dincr-app-lock-benefits">
          <div><Fingerprint size={20}/><span><strong>{tx("Tu cara o huella", "Your face or fingerprint")}</strong><small>{tx("DINCR nunca recibe ni guarda tus datos biométricos.", "DINCR never receives or stores your biometric data.")}</small></span></div>
          <div><TimerReset size={20}/><span><strong>{tx("Bloqueo a los 5 minutos", "Locks after 5 minutes")}</strong><small>{tx("Las salidas rápidas no te interrumpirán.", "Brief app switches won’t interrupt you.")}</small></span></div>
          <div><ShieldCheck size={20}/><span><strong>{tx("Sin cerrar tu sesión", "Without signing you out")}</strong><small>{tx("Solo confirmás que sos vos para volver a entrar.", "You only confirm it’s you to get back in.")}</small></span></div>
        </div>
        {status && !status.isAvailable && <div className="dincr-app-lock-error" role="alert">{tx("No encontramos biometría configurada. Podés activarla luego desde Ajustes de DINCR.", "No configured biometrics were found. You can enable it later from DINCR Settings.")}</div>}
        {message && <div className="dincr-app-lock-error" role="alert">{message}</div>}
        <button className="dincr-app-unlock-button" type="button" disabled={working || status === null || !status?.isAvailable} onClick={activate}>
          <Fingerprint size={21} /> {working ? tx("Verificando…", "Verifying…") : tx("Activar acceso seguro", "Enable secure access")}
        </button>
        <button className="dincr-app-lock-skip-button" type="button" disabled={working} onClick={skip}>{tx("Ahora no", "Not now")}</button>
      </section>
    </main>
  );
}
