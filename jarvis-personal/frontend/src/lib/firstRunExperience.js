const WELCOME_VERSION = "v1";
const WELCOME_KEY_PREFIX = `dincr:first-run-welcome:${WELCOME_VERSION}:`;

const welcomeKey = (accountId) => `${WELCOME_KEY_PREFIX}${String(accountId || "anonymous")}`;

export function shouldShowDincrWelcome(accountId) {
  try {
    return window.localStorage.getItem(welcomeKey(accountId)) !== "seen";
  } catch {
    return true;
  }
}

export function markDincrWelcomeSeen(accountId) {
  try {
    window.localStorage.setItem(welcomeKey(accountId), "seen");
  } catch {
    // Storage may be unavailable in hardened browsers. This must never block DINCR.
  }
}
