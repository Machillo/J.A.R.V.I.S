import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Minimal browser globals: mailOAuth.js runs in the Capacitor WebView.
const store = new Map();
const events = [];
globalThis.window = {
  sessionStorage: {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  },
  dispatchEvent: (event) => events.push(event),
};
globalThis.CustomEvent ??= class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } };

const { parseMailOAuthReturn, redeemPendingMailOAuth, takeMailOAuthOutcome } = await import("../src/lib/mailOAuth.js");

const flow = "0f6b6c1e-1111-4222-8333-944444444444";
assert.deepEqual(parseMailOAuthReturn(`com.finva.app://gmail/callback?gmail=authorized&flow=${flow}&completion=one-time`),
  { provider: "gmail", status: "authorized", flow, completion: "one-time" });
assert.equal(parseMailOAuthReturn(`com.dincr.app://gmail/callback?microsoft=invalid_state`).provider, "microsoft");
assert.equal(parseMailOAuthReturn("https://evil.example/?gmail=authorized&flow=x&completion=y"), null);

// The signed-in session redeems the completion exactly once.
const calls = [];
const complete = async (...args) => { calls.push(args); return { status: "connected" }; };
const pending = `com.dincr.app://gmail/callback?microsoft=authorized&flow=${flow}&completion=one-time`;
window.sessionStorage.setItem("dincr:mail-oauth-pending", pending);
assert.deepEqual(await redeemPendingMailOAuth(complete), { provider: "microsoft", ok: true });
assert.deepEqual(calls, [[flow, "one-time"]]);
assert.deepEqual(takeMailOAuthOutcome(), { provider: "microsoft", ok: true });
assert.equal(takeMailOAuthOutcome(), null, "an outcome is shown once");
window.sessionStorage.setItem("dincr:mail-oauth-pending", pending); // relaunch replays the same deep link
assert.equal(await redeemPendingMailOAuth(complete), null);
assert.equal(calls.length, 1, "the same flow is never redeemed twice");

// Provider errors are reported without calling the API.
window.sessionStorage.setItem("dincr:mail-oauth-pending", "com.finva.app://gmail/callback?gmail=denied");
assert.deepEqual(await redeemPendingMailOAuth(complete), { provider: "gmail", ok: false, code: "denied" });
assert.equal(calls.length, 1);

// A rejected completion (another account, expired) surfaces the server message.
const rejecting = async () => { throw new Error("Esta autorización de correo no pertenece a tu cuenta DINCR."); };
window.sessionStorage.setItem("dincr:mail-oauth-pending", `com.finva.app://gmail/callback?gmail=authorized&flow=${flow.replace("f6", "a7")}&completion=c`);
const rejected = await redeemPendingMailOAuth(rejecting);
assert.equal(rejected.ok, false);
assert.match(rejected.message, /no pertenece a tu cuenta/);
assert.equal(await redeemPendingMailOAuth(complete), null, "nothing pending");

// Wiring: UsersApp redeems for every DINCR session; the screen only reports the outcome.
const usersApp = readFileSync(new URL("../src/users/UsersApp.jsx", import.meta.url), "utf8");
const gmail = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/users/services/jarvisApi.js", import.meta.url), "utf8");
assert.match(usersApp, /captureMailOAuthReturns\(\)/);
assert.match(usersApp, /redeemPendingMailOAuth\(completeVipMailConnection\)/);
assert.match(api, /completeVipMailConnection = \(flow, completion\) => json\("\/user-product\/vip\/mail\/oauth\/complete", "POST"/);
assert.doesNotMatch(gmail, /appUrlOpen/, "only one place may redeem a single-use completion");
assert.match(gmail, /takeMailOAuthOutcome\(\)/);

console.log("DINCR mail OAuth completion is redeemed once by the signed-in session.");
