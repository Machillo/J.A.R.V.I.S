import { recordError } from "./telemetry";
import { captureIncident } from "./incidentReporter";
import { deviceLanguage, tx } from "./locale";

export const SUPPORT_CONTEXT_KEY = "finva:support-context";

const genericMessage = () => tx("No pudimos completar esta acción. Intentá nuevamente o pedí ayuda a soporte.", "We couldn’t complete this action. Try again or ask support for help.");

export class FinvaApiError extends Error {
  constructor(message, { status, errorId, requestId, retryCount, path, method, technicalMessage, code } = {}) {
    super(message);
    this.name = "FinvaApiError";
    this.status = status;
    this.errorId = errorId || "";
    this.requestId = requestId || errorId || "";
    this.retryCount = retryCount || 0;
    this.path = path || "";
    this.method = method || "GET";
    this.technicalMessage = technicalMessage || "";
    this.code = code || "";
  }
}

export function apiError(response, payload, path, method = "GET", autoReport = false) {
  const rawDetail = typeof payload === "string" ? payload : payload?.detail || payload?.error || "";
  const detail = typeof rawDetail === "object" ? rawDetail?.message || "" : rawDetail;
  const deletionId = typeof rawDetail === "object" ? rawDetail?.deletion_id || "" : "";
  const deletionStage = typeof rawDetail === "object" ? rawDetail?.stage || "" : "";
  const code = typeof rawDetail === "object" ? rawDetail?.code || "" : "";
  const status = response?.status || 0;
  // Backend details are written in Spanish; English sessions get the status message instead.
  const shownDetail = deviceLanguage() === "es" ? detail : "";
  let message = genericMessage();
  if (status === 401) message = tx("Tu sesión venció. Iniciá sesión nuevamente.", "Your session expired. Please sign in again.");
  else if (status === 402) message = tx("Esta función necesita una suscripción activa.", "This feature needs an active subscription.");
  else if (status === 403) message = shownDetail || tx("No tenés permiso para realizar esta acción.", "You don’t have permission to do this.");
  else if (status === 404) message = shownDetail || tx("No encontramos la información solicitada.", "We couldn’t find what you asked for.");
  else if (status === 409 || status === 422) message = shownDetail || tx("Revisá la información e intentá nuevamente.", "Check the information and try again.");
  else if (status >= 400 && status < 500) message = shownDetail || tx("No pudimos procesar la solicitud.", "We couldn’t process the request.");
  // Account deletion states carry an explicit backend message already in the session language.
  if (code === "account_deletion_pending" && detail) message = detail;

  const error = new FinvaApiError(message, {
    status,
    errorId: deletionId || (typeof payload === "object" ? payload?.error_id : ""),
    requestId: response?.finvaRequestId || response?.headers?.get?.("X-Request-ID") || payload?.request_id || "",
    retryCount: response?.finvaRetryCount || 0,
    path,
    method,
    technicalMessage: deletionStage ? `${detail} [${deletionStage}]` : detail,
    code,
  });
  if (autoReport && (status >= 500 || status === 0)) {
    const incident = {
      screen: path,
      errorReference: error.errorId,
      requestId: error.requestId,
      retryCount: error.retryCount,
      status,
      path,
      method,
      errorType: `http_${status || "network"}`,
      summary: tx("DINCR no pudo completar una acción.", "DINCR couldn’t complete an action."),
    };
    window.dispatchEvent(new CustomEvent("finva:api-error", { detail: incident }));
    captureIncident(incident);
  }
  recordError(error, `api:${path || "unknown"}`);
  return error;
}

export function apiNetworkError(cause, path, method = "GET", autoReport = true) {
  const queued = Boolean(cause?.finvaOperationQueued);
  const error = new FinvaApiError(queued
    ? tx("Guardamos este cambio en el dispositivo. DINCR lo enviará cuando vuelva la conexión.", "We saved this change on your device. DINCR will send it when you’re back online.")
    : genericMessage(), {
    status: 0,
    errorId: cause?.finvaRequestId || "",
    requestId: cause?.finvaRequestId || "",
    retryCount: cause?.finvaRetryCount || 0,
    path,
    method,
    technicalMessage: cause?.name || "NetworkError",
  });
  error.operationQueued = queued;
  const incident = {
    screen: path, errorReference: error.errorId, requestId: error.requestId,
    retryCount: error.retryCount, status: 0, path, method,
    errorType: cause?.name || "network_error", summary: tx("DINCR perdió comunicación con el servicio.", "DINCR lost connection to the service."),
  };
  if (autoReport) {
    window.dispatchEvent(new CustomEvent("finva:api-error", { detail: incident }));
    captureIncident(incident);
  }
  recordError(error, `api:${path || "unknown"}`);
  return error;
}

export function openSupport(context = {}) {
  const safeContext = {
    kind: context.kind || "problem",
    screen: String(context.screen || window.location.pathname || "").slice(0, 80),
    errorReference: String(context.errorReference || "").slice(0, 80),
    summary: String(context.summary || "").slice(0, 240),
  };
  window.sessionStorage.setItem(SUPPORT_CONTEXT_KEY, JSON.stringify(safeContext));
  window.dispatchEvent(new CustomEvent("finva:open-support", { detail: safeContext }));
}
