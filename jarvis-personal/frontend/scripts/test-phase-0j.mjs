import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_APP_LOCK_TIMEOUT, hasSeenAppLockOnboarding, markAppLockOnboardingSeen, normalizeAppLockConfig, shouldLockAfterInactivity } from "../src/lib/appLock.js";

assert.equal(DEFAULT_APP_LOCK_TIMEOUT, 300_000, "FINVA owns a five-minute security timeout");
assert.equal(normalizeAppLockConfig({ enabled: true, timeoutMs: 0 }).timeoutMs, 300_000, "legacy custom timeouts migrate to five minutes");
assert.equal(shouldLockAfterInactivity(300_000, 299_999), false, "five-minute grace period is respected");
assert.equal(shouldLockAfterInactivity(300_000, 300_000), true, "five-minute timeout locks at its boundary");
assert.equal(shouldLockAfterInactivity(300_000, -1), false, "invalid elapsed time never locks");

const localValues = new Map();
global.window = { localStorage: { getItem: (key) => localValues.get(key) || null, setItem: (key, value) => localValues.set(key, value) } };
assert.equal(hasSeenAppLockOnboarding("existing-user"), false, "existing users see the new onboarding once");
markAppLockOnboardingSeen("existing-user");
assert.equal(hasSeenAppLockOnboarding("existing-user"), true, "completed onboarding does not repeat on the same device");

const app = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const settings = readFileSync(new URL("../src/users/components/AppLockSettings.jsx", import.meta.url), "utf8");
const lock = readFileSync(new URL("../src/components/FinvaAppLock.jsx", import.meta.url), "utf8");
const appLock = readFileSync(new URL("../src/lib/appLock.js", import.meta.url), "utf8");
const onboarding = readFileSync(new URL("../src/components/FinvaAppLockOnboarding.jsx", import.meta.url), "utf8");
const iosConfig = readFileSync(new URL("../capacitor.ios.finva.json", import.meta.url), "utf8");
const infoPlist = readFileSync(new URL("../ios-finva/App/App/Info.plist", import.meta.url), "utf8");
const iosProductScript = readFileSync(new URL("./ios-product.mjs", import.meta.url), "utf8");

assert.match(app, /<FinvaAppLock/, "authenticated FINVA is protected by the local lock gate");
assert.match(settings, /Bloquear ahora/, "settings provide a manual lock action");
assert.doesNotMatch(settings, /<select/, "users cannot weaken the FINVA-owned timeout");
assert.match(settings, /5 minutos/, "settings explain the fixed five-minute timeout");
assert.match(lock, /appStateChange/, "lock reacts to native background and resume events");
assert.match(lock, /hasSeenAppLockOnboarding/, "new and existing users receive the one-time security onboarding");
assert.match(lock, /Cerrar sesión/, "locked screen keeps logout separate from unlock");
assert.match(onboarding, /Activar acceso seguro/, "onboarding offers direct biometric activation");
assert.match(onboarding, /Ahora no/, "onboarding never traps a user without compatible biometrics");
assert.match(iosConfig, /capacitor-biometric-auth/, "FINVA iOS bundles the biometric plugin");
assert.match(infoPlist, /NSFaceIDUsageDescription/, "FINVA declares why it uses Face ID");
assert.match(iosProductScript, /verifyNativeBundle\(\)/, "the iOS workflow verifies the generated native bundle before opening Xcode");
assert.match(appLock, /VITE_NATIVE_APP_ID.*com\.finva\.app/, "FINVA iOS does not skip security while the Capacitor bridge is attaching");
assert.match(iosProductScript, /finva:app-lock-onboarding:v2/, "the FINVA iOS workflow rejects a stale bundle without biometric onboarding");

console.log("Phase 0J biometric lock contract passed.");
