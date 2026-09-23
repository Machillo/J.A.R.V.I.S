import { App as CapacitorApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { isMailOAuthCallback } from "./appIdentity.js";

// Gmail/Outlook consent happens in the system browser, which does not share the
// app's session. The backend parks the authorization and returns here with a
// one-time completion code; this DINCR session redeems it, proving it is the
// session that started the connection. Each flow is redeemed at most once.
export const MAIL_OAUTH_RETURN_EVENT = "dincr:mail-oauth-return";
export const MAIL_OAUTH_RESULT_EVENT = "dincr:mail-oauth-result";
const PENDING_KEY = "dincr:mail-oauth-pending";
const DONE_KEY = "dincr:mail-oauth-done";

let capturing = false;
let lastOutcome = null;

const storage = () => { try { return window.sessionStorage; } catch { return null; } };

export function parseMailOAuthReturn(url) {
  if (!isMailOAuthCallback(url)) return null;
  const params = new URL(url).searchParams;
  const provider = params.has("microsoft") ? "microsoft" : "gmail";
  return { provider, status: params.get(provider) || "", flow: params.get("flow") || "", completion: params.get("completion") || "" };
}

export function captureMailOAuthReturns() {
  if (capturing || !Capacitor.isNativePlatform()) return;
  capturing = true;
  const remember = async (url) => {
    if (!isMailOAuthCallback(url)) return;
    try { await Browser.close(); } catch { /* the browser may already be closed */ }
    storage()?.setItem(PENDING_KEY, url);
    window.dispatchEvent(new CustomEvent(MAIL_OAUTH_RETURN_EVENT));
  };
  CapacitorApp.addListener("appUrlOpen", ({ url }) => remember(url));
  // Android may relaunch the app from the deep link while the browser is open.
  CapacitorApp.getLaunchUrl().then((launch) => launch?.url && remember(launch.url)).catch(() => {});
}

function alreadyRedeemed(flow) {
  const done = new Set(JSON.parse(storage()?.getItem(DONE_KEY) || "[]"));
  if (done.has(flow)) return true;
  storage()?.setItem(DONE_KEY, JSON.stringify([...done, flow].slice(-10)));
  return false;
}

// Redeem the pending return (if any) with the given API call; returns the outcome.
export async function redeemPendingMailOAuth(completeConnection) {
  const url = storage()?.getItem(PENDING_KEY);
  if (!url) return null;
  storage()?.removeItem(PENDING_KEY);
  const pending = parseMailOAuthReturn(url);
  if (!pending) return null;
  let outcome;
  if (pending.status !== "authorized" || !pending.flow || !pending.completion) {
    outcome = { provider: pending.provider, ok: false, code: pending.status || "unknown" };
  } else if (alreadyRedeemed(pending.flow)) {
    return null;
  } else {
    try {
      await completeConnection(pending.flow, pending.completion);
      outcome = { provider: pending.provider, ok: true };
    } catch (error) {
      outcome = { provider: pending.provider, ok: false, code: "completion_failed", message: error?.message || "" };
    }
  }
  lastOutcome = outcome;
  window.dispatchEvent(new CustomEvent(MAIL_OAUTH_RESULT_EVENT, { detail: outcome }));
  return outcome;
}

export function takeMailOAuthOutcome() {
  const outcome = lastOutcome;
  lastOutcome = null;
  return outcome;
}
