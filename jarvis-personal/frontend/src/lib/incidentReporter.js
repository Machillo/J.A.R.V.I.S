import { Capacitor } from "@capacitor/core";
import { API_URL } from "./apiUrl";
import { authenticatedFetch } from "./authenticatedFetch";
import { endpointModule } from "./analyticsContract";
import { captureProductEvent } from "./productAnalytics";

const QUEUE_KEY = "finva:incident-queue:v1";
const DEDUPE_MS = 15 * 60 * 1000;
let flushing = false;

const clean = (value, limit) => String(value || "").replace(/[\r\n\t]+/g, " ").slice(0, limit);
const readQueue = () => {
  try { return JSON.parse(window.localStorage.getItem(QUEUE_KEY) || "[]"); }
  catch { return []; }
};
const writeQueue = (items) => window.localStorage.setItem(QUEUE_KEY, JSON.stringify(items.slice(-20)));
const fingerprint = (incident) => [incident.method, incident.path, incident.status, incident.errorType, incident.appVersion].join("|");
const safePath = (value) => clean(value, 240)
  .split(/[?#]/, 1)[0]
  .replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, ":id")
  .replace(/\/\d+(?=\/|$)/g, "/:id")
  .slice(0, 160) || "/unknown";

const safeIncident = (incident) => ({
  path: safePath(incident.path),
  method: clean(incident.method || "GET", 10).toUpperCase(),
  status: Number(incident.status) || 0,
  request_id: clean(incident.requestId, 80),
  error_reference: clean(incident.errorReference, 80) || undefined,
  error_type: clean(incident.errorType || "api_error", 80),
  app_version: clean(import.meta.env.VITE_APP_VERSION || "dev", 30),
  platform: clean(Capacitor.getPlatform(), 30),
  screen: clean(window.sessionStorage.getItem("finva:current-screen") || window.location.pathname, 80),
  retry_count: Math.min(Math.max(Number(incident.retryCount) || 0, 0), 3),
});

export async function flushIncidentQueue() {
  if (flushing) return null;
  const queue = readQueue();
  if (!queue.length) return null;
  flushing = true;
  try {
    const incident = queue[0];
    const payload = { ...incident };
    delete payload.fingerprint;
    delete payload.queued_at;
    const response = await authenticatedFetch(`${API_URL}/product-ops/incidents`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Request-ID": incident.request_id },
      body: JSON.stringify(payload),
    });
    if (!response.ok) return null;
    const result = await response.json();
    writeQueue(queue.slice(1));
    window.dispatchEvent(new CustomEvent("finva:incident-reported", { detail: result }));
    return result;
  } catch {
    return null;
  } finally {
    flushing = false;
  }
}

export function captureIncident(rawIncident) {
  const incident = safeIncident(rawIncident);
  if (!incident.request_id || incident.path === "/product-ops/incidents") return Promise.resolve(null);
  const now = Date.now();
  const key = fingerprint(incident);
  const queue = readQueue().filter((item) => now - Number(item.queued_at || 0) < DEDUPE_MS);
  if (!queue.some((item) => item.fingerprint === key)) {
    queue.push({ ...incident, fingerprint: key, queued_at: now });
    writeQueue(queue);
    // Same de-duplication window as the incident itself: one event per failure, not per retry.
    captureProductEvent("api_error", {
      endpoint: endpointModule(incident.path), method: incident.method, status_code: incident.status || undefined,
      error_category: incident.status >= 500 ? "server" : incident.status >= 400 ? "client" : "network",
    });
  }
  return flushIncidentQueue();
}
