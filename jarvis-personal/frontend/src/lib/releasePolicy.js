import { API_URL } from "./apiUrl";

export const APP_VERSION = import.meta.env.VITE_APP_VERSION || "0.0.0";
const DISMISS_PREFIX = "finva:release-dismissed:";

export async function getReleasePolicy(platform, version = APP_VERSION) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8_000);
  try {
    const params = new URLSearchParams({ platform, version });
    const response = await fetch(`${API_URL}/product-ops/release-policy?${params}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Release policy request failed (${response.status})`);
    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

export function isReleaseDismissed(policy) {
  return policy?.latest_version
    ? window.localStorage.getItem(`${DISMISS_PREFIX}${policy.platform}`) === policy.latest_version
    : false;
}

export function dismissRelease(policy) {
  if (policy?.latest_version) {
    window.localStorage.setItem(`${DISMISS_PREFIX}${policy.platform}`, policy.latest_version);
  }
}
