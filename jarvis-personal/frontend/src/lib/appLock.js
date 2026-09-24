import { Capacitor } from "@capacitor/core";
import {
  AndroidBiometryStrength,
  BiometricAuth,
  BiometryErrorType,
  BiometryType,
} from "@aparajita/capacitor-biometric-auth";
import { isDincrAppId } from "./appIdentity.js";
import { tx } from "./locale.js";

export const APP_LOCK_CHANGED_EVENT = "finva:app-lock-changed";
export const APP_LOCK_REQUESTED_EVENT = "finva:app-lock-requested";
export const DEFAULT_APP_LOCK_TIMEOUT = 300_000;

const storageKey = (userId) => `finva:app-lock:${userId}`;
const onboardingKey = (userId) => `finva:app-lock-onboarding:v2:${userId}`;

export function isNativeAppLockSupported() {
  // Capacitor's bridge can report `web` during the first iOS render. The
  // product-specific build id is deterministic and keeps the DINCR gate from
  // being skipped while WebKit finishes attaching the native bridge.
  return Capacitor.isNativePlatform() || isDincrAppId(import.meta.env?.VITE_NATIVE_APP_ID);
}

export function normalizeAppLockConfig(value = {}) {
  return { enabled: Boolean(value.enabled), timeoutMs: DEFAULT_APP_LOCK_TIMEOUT };
}

export function getAppLockConfig(userId) {
  if (!userId) return normalizeAppLockConfig();
  try {
    return normalizeAppLockConfig(JSON.parse(window.localStorage.getItem(storageKey(userId)) || "{}"));
  } catch {
    return normalizeAppLockConfig();
  }
}

export function saveAppLockConfig(userId, config) {
  const next = normalizeAppLockConfig(config);
  if (!userId) return next;
  window.localStorage.setItem(storageKey(userId), JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(APP_LOCK_CHANGED_EVENT, { detail: { userId, config: next } }));
  return next;
}

export function requestAppLock(userId) {
  window.dispatchEvent(new CustomEvent(APP_LOCK_REQUESTED_EVENT, { detail: { userId } }));
}

export function hasSeenAppLockOnboarding(userId) {
  if (!userId) return true;
  return window.localStorage.getItem(onboardingKey(userId)) === "1";
}

export function markAppLockOnboardingSeen(userId) {
  if (userId) window.localStorage.setItem(onboardingKey(userId), "1");
}

export function shouldLockAfterInactivity(timeoutMs, inactiveForMs) {
  if (!Number.isFinite(inactiveForMs) || inactiveForMs < 0) return false;
  return Number(timeoutMs) === 0 || inactiveForMs >= Number(timeoutMs);
}

export async function getBiometryStatus() {
  if (!isNativeAppLockSupported()) {
    return { isAvailable: false, deviceIsSecure: false, biometryType: BiometryType.none, reason: "native_required" };
  }
  return BiometricAuth.checkBiometry();
}

export function biometryLabel(type) {
  if (type === BiometryType.faceId || type === BiometryType.faceAuthentication) return "Face ID";
  if (type === BiometryType.touchId) return "Touch ID";
  if (type === BiometryType.fingerprintAuthentication) return tx("huella", "fingerprint");
  if (type === BiometryType.irisAuthentication) return tx("iris", "iris");
  return tx("biometría", "biometrics");
}

export function appLockErrorMessage(error) {
  const code = error?.code;
  if (code === BiometryErrorType.userCancel || code === BiometryErrorType.systemCancel || code === BiometryErrorType.appCancel) {
    return tx("La verificación fue cancelada.", "Verification was canceled.");
  }
  if (code === BiometryErrorType.biometryNotEnrolled) return tx("Primero configurá la biometría en los ajustes del teléfono.", "Set up biometrics in your phone settings first.");
  if (code === BiometryErrorType.biometryLockout) return tx("La biometría está bloqueada temporalmente. Usá el código del teléfono.", "Biometrics are temporarily locked. Use your phone passcode.");
  if (code === BiometryErrorType.passcodeNotSet || code === BiometryErrorType.noDeviceCredential) return tx("El teléfono necesita un código de desbloqueo configurado.", "Your phone needs a screen lock passcode.");
  return tx("No pudimos verificar tu identidad. Intentá nuevamente.", "We couldn’t verify your identity. Please try again.");
}

export async function authenticateAppLock() {
  await BiometricAuth.authenticate({
    reason: tx("Desbloquear DINCR", "Unlock DINCR"),
    cancelTitle: tx("Cancelar", "Cancel"),
    allowDeviceCredential: true,
    iosFallbackTitle: tx("Usar código", "Use passcode"),
    androidTitle: tx("Desbloquear DINCR", "Unlock DINCR"),
    androidSubtitle: tx("Confirmá que sos vos para ver tus finanzas", "Confirm it’s you to see your finances"),
    androidConfirmationRequired: false,
    androidBiometryStrength: AndroidBiometryStrength.weak,
  });
}
