import { Capacitor } from "@capacitor/core";
import {
  AndroidBiometryStrength,
  BiometricAuth,
  BiometryErrorType,
  BiometryType,
} from "@aparajita/capacitor-biometric-auth";

export const APP_LOCK_CHANGED_EVENT = "dincr:app-lock-changed";
export const APP_LOCK_REQUESTED_EVENT = "dincr:app-lock-requested";
export const DEFAULT_APP_LOCK_TIMEOUT = 300_000;

const storageKey = (userId) => `dincr:app-lock:${userId}`;
const onboardingKey = (userId) => `dincr:app-lock-onboarding:v2:${userId}`;

export function isNativeAppLockSupported() {
  // Capacitor's bridge can report `web` during the first iOS render. The
  // product-specific build id is deterministic and keeps the DINCR gate from
  // being skipped while WebKit finishes attaching the native bridge.
  return Capacitor.isNativePlatform() || import.meta.env?.VITE_NATIVE_APP_ID === "com.dincr.app";
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
    reason: "Desbloquear DINCR",
    cancelTitle: "Cancelar",
    allowDeviceCredential: true,
    iosFallbackTitle: "Usar código",
    androidTitle: "Desbloquear DINCR",
    androidSubtitle: "Confirmá que sos vos para ver tus finanzas",
    androidConfirmationRequired: false,
    androidBiometryStrength: AndroidBiometryStrength.weak,
  });
}
