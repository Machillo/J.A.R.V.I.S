import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { shouldLockAfterInactivity } from "../src/lib/appLock.js";

assert.equal(shouldLockAfterInactivity(0, 0), true, "immediate mode locks on resume");
assert.equal(shouldLockAfterInactivity(60_000, 59_999), false, "one-minute grace period is respected");
assert.equal(shouldLockAfterInactivity(60_000, 60_000), true, "one-minute timeout locks at its boundary");
assert.equal(shouldLockAfterInactivity(300_000, -1), false, "invalid elapsed time never locks");

const app = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const settings = readFileSync(new URL("../src/users/components/AppLockSettings.jsx", import.meta.url), "utf8");
const lock = readFileSync(new URL("../src/components/FinvaAppLock.jsx", import.meta.url), "utf8");
const iosConfig = readFileSync(new URL("../capacitor.ios.finva.json", import.meta.url), "utf8");
const infoPlist = readFileSync(new URL("../ios-finva/App/App/Info.plist", import.meta.url), "utf8");

assert.match(app, /<FinvaAppLock/, "authenticated FINVA is protected by the local lock gate");
assert.match(settings, /Bloquear ahora/, "settings provide a manual lock action");
assert.match(settings, /APP_LOCK_TIMEOUTS/, "settings expose the supported timeout choices");
assert.match(lock, /appStateChange/, "lock reacts to native background and resume events");
assert.match(lock, /Cerrar sesión/, "locked screen keeps logout separate from unlock");
assert.match(iosConfig, /capacitor-biometric-auth/, "FINVA iOS bundles the biometric plugin");
assert.match(infoPlist, /NSFaceIDUsageDescription/, "FINVA declares why it uses Face ID");

console.log("Phase 0J biometric lock contract passed.");
