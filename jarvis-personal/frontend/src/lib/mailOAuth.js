import { App as CapacitorApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { isMailOAuthCallback } from "./appIdentity.js";

// Gmail/Outlook consent happens in the system browser, which does not share the
// app's session. The backend parks the authorization and returns here with a
// one-time completion code; this DINCR session redeems it, proving it is the
// session that started the connection.
//
// The same return link can reach the app more than once: Capacitor delivers a
// cold-start link both as a retained appUrlOpen event and through
// getLaunchUrl(), Android keeps the launch intent for the whole activity life
// (and replays it when the activity is recreated), and iOS getLaunchUrl()
// returns the last URL opened in the process. Every backend response carries a
// unique `ret`, so each delivery is handled exactly once: returns are queued,
// processed one at a time, and recorded as handled only after a definitive
// result. A completion that fails on the network stays queued and is retried;
// the backend confirms an already-completed flow for the initiating session.
export const MAIL_OAUTH_RETURN_EVENT = "dincr:mail-oauth-return";
export const MAIL_OAUTH_RESULT_EVENT = "dincr:mail-oauth-result";
const PENDING_KEY = "dincr:mail-oauth-pending";
const HANDLED_KEY = "dincr:mail-oauth-handled";
const CONNECTED_KEY = "dincr:mail-oauth-connected";
const HANDLED_LIMIT = 50;
// A replayed provider redirect right after a successful connection is not news.
const RECENT_CONNECTION_MS = 15 * 60 * 1000;

// One capture per App plugin instance, however often the app shell mounts.
const capturedApps = new WeakSet();
let redeeming = null;
let lastOutcome = null;

const session = () => { try { return window.sessionStorage; } catch { return null; } };
// Handled returns must survive a process restart: Android and iOS can hand the
// same launch URL to a new WebView. Only identifiers are kept, never the code.
const durable = () => { try { return window.localStorage || window.sessionStorage; } catch { return null; } };
const readJson = (store, key, fallback) => { try { return JSON.parse(store?.getItem(key) || "") ?? fallback; } catch { return fallback; } };
const writeJson = (store, key, value) => { try { store?.setItem(key, JSON.stringify(value)); } catch { /* storage full or blocked */ } };

export function parseMailOAuthReturn(url) {
  if (!isMailOAuthCallback(url)) return null;
  const params = new URL(url).searchParams;
  const provider = params.has("microsoft") ? "microsoft" : "gmail";
  return {
    provider,
    status: params.get(provider) || "",
    flow: params.get("flow") || "",
    completion: params.get("completion") || "",
    ret: params.get("ret") || "",
  };
}

// One key per backend response. Older backends did not send `ret`; the flow id
// still identifies an authorized return.
const returnKey = (item) => [item.provider, item.status, item.flow, item.ret].join(":");

const isHandled = (key) => readJson(durable(), HANDLED_KEY, []).includes(key);
const markHandled = (key) => writeJson(durable(), HANDLED_KEY, [...readJson(durable(), HANDLED_KEY, []).filter((item) => item !== key), key].slice(-HANDLED_LIMIT));
const pendingUrls = () => readJson(session(), PENDING_KEY, []).filter((url) => typeof url === "string");
const dropPending = (url) => writeJson(session(), PENDING_KEY, pendingUrls().filter((item) => item !== url));
const markConnected = (provider) => writeJson(durable(), CONNECTED_KEY, { ...readJson(durable(), CONNECTED_KEY, {}), [provider]: Date.now() });
const connectedRecently = (provider) => Date.now() - Number(readJson(durable(), CONNECTED_KEY, {})[provider] || 0) < RECENT_CONNECTION_MS;

// Queue a return link (idempotent). Returns true when it is new work.
export function rememberMailOAuthReturn(url) {
  const item = parseMailOAuthReturn(url);
  if (!item || isHandled(returnKey(item))) return false;
  const pending = pendingUrls();
  if (pending.includes(url)) return false;
  writeJson(session(), PENDING_KEY, [...pending, url]);
  return true;
}

// Plugins are injectable so the lifecycle can be exercised outside a device.
export function captureMailOAuthReturns({ app = CapacitorApp, browser = Browser, isNative = () => Capacitor.isNativePlatform() } = {}) {
  if (capturedApps.has(app) || !isNative()) return;
  capturedApps.add(app);
  const receive = (url) => {
    if (!isMailOAuthCallback(url)) return;
    Promise.resolve().then(() => browser.close()).catch(() => { /* the browser may already be closed */ });
    if (rememberMailOAuthReturn(url)) window.dispatchEvent(new CustomEvent(MAIL_OAUTH_RETURN_EVENT));
  };
  app.addListener("appUrlOpen", ({ url }) => receive(url));
  // A cold start delivers the link here too; the handled registry ignores repeats.
  app.getLaunchUrl().then((launch) => launch?.url && receive(launch.url)).catch(() => {});
}

// Network failures and server errors leave the flow redeemable; retrying is safe.
const isRetryable = (error) => !error?.status || error.status >= 500 || error.status === 408 || error.status === 429;

async function processReturn(url, completeConnection) {
  const item = parseMailOAuthReturn(url);
  if (!item) { dropPending(url); return null; }
  const key = returnKey(item);
  if (isHandled(key)) { dropPending(url); return null; }

  if (item.status === "authorized" && item.flow && item.completion) {
    try {
      await completeConnection(item.flow, item.completion);
    } catch (error) {
      if (isRetryable(error)) return { provider: item.provider, ok: false, code: "completion_pending" };
      markHandled(key);
      dropPending(url);
      return { provider: item.provider, ok: false, code: "completion_failed", message: error?.message || "" };
    }
    markHandled(key);
    dropPending(url);
    markConnected(item.provider);
    return { provider: item.provider, ok: true };
  }

  markHandled(key);
  dropPending(url);
  if (item.status === "already_processed" && connectedRecently(item.provider)) return null;
  return { provider: item.provider, ok: false, code: item.status || "unknown" };
}

// Redeem queued returns with the given API call; resolves to the last outcome.
// Concurrent calls (duplicate events, React remounts) share one run.
export function redeemPendingMailOAuth(completeConnection) {
  if (redeeming) return redeeming;
  const attempted = new Set();
  const nextUrl = () => pendingUrls().find((item) => !attempted.has(item));
  redeeming = (async () => {
    let outcome = null;
    for (let url = nextUrl(); url; url = nextUrl()) {
      attempted.add(url);
      const result = await processReturn(url, completeConnection);
      if (!result) continue;
      outcome = result;
      lastOutcome = result;
      window.dispatchEvent(new CustomEvent(MAIL_OAUTH_RESULT_EVENT, { detail: result }));
    }
    return outcome;
  })().finally(() => {
    redeeming = null;
    // A link queued while this run was finishing gets its own run.
    if (nextUrl()) redeemPendingMailOAuth(completeConnection);
  });
  return redeeming;
}

export function takeMailOAuthOutcome() {
  const outcome = lastOutcome;
  lastOutcome = null;
  return outcome;
}
