import { Capacitor } from "@capacitor/core";
import {
  AndroidBiometryStrength,
  BiometricAuth,
  BiometryErrorType,
  BiometryType,
} from "@aparajita/capacitor-biometric-auth";

export const APP_LOCK_CHANGED_EVENT = "finva:app-lock-changed";
export const APP_LOCK_REQUESTED_EVENT = "finva:app-lock-requested";
export const APP_LOCK_TIMEOUTS = [0, 60_000, 300_000, 900_000, 3_600_000];
export const DEFAULT_APP_LOCK_TIMEOUT = 300_000;

const storageKey = (userId) => `finva:app-lock:${userId}`;

export function isNativeAppLockSupported() {
  return Capacitor.isNativePlatform();
}

export function normalizeAppLockConfig(value = {}) {
  const timeoutMs = APP_LOCK_TIMEOUTS.includes(Number(value.timeoutMs))
    ? Number(value.timeoutMs)
    : DEFAULT_APP_LOCK_TIMEOUT;
  return { enabled: Boolean(value.enabled), timeoutMs };
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
  if (type === BiometryType.fingerprintAuthentication) return "huella";
  if (type === BiometryType.irisAuthentication) return "iris";
  return "biometría";
}

export function appLockErrorMessage(error) {
  const code = error?.code;
  if (code === BiometryErrorType.userCancel || code === BiometryErrorType.systemCancel || code === BiometryErrorType.appCancel) {
    return "La verificación fue cancelada.";
  }
  if (code === BiometryErrorType.biometryNotEnrolled) return "Primero configurá la biometría en los ajustes del teléfono.";
  if (code === BiometryErrorType.biometryLockout) return "La biometría está bloqueada temporalmente. Usá el código del teléfono.";
  if (code === BiometryErrorType.passcodeNotSet || code === BiometryErrorType.noDeviceCredential) return "El teléfono necesita un código de desbloqueo configurado.";
  return "No pudimos verificar tu identidad. Intentá nuevamente.";
}

export async function authenticateAppLock() {
  await BiometricAuth.authenticate({
    reason: "Desbloquear FINVA",
    cancelTitle: "Cancelar",
    allowDeviceCredential: true,
    iosFallbackTitle: "Usar código",
    androidTitle: "Desbloquear FINVA",
    androidSubtitle: "Confirmá que sos vos para ver tus finanzas",
    androidConfirmationRequired: false,
    androidBiometryStrength: AndroidBiometryStrength.weak,
  });
}
