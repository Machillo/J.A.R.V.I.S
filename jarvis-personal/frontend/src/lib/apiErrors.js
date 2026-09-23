import { recordError } from "./telemetry";
import { captureIncident } from "./incidentReporter";

export const SUPPORT_CONTEXT_KEY = "dincr:support-context";

const GENERIC_MESSAGE = "No pudimos completar esta acción. Intentá nuevamente o pedí ayuda a soporte.";

export class DincrApiError extends Error {
  constructor(message, { status, errorId, requestId, retryCount, path, method, technicalMessage } = {}) {
    super(message);
    this.name = "DincrApiError";
    this.status = status;
    this.errorId = errorId || "";
    this.requestId = requestId || errorId || "";
    this.retryCount = retryCount || 0;
    this.path = path || "";
    this.method = method || "GET";
    this.technicalMessage = technicalMessage || "";
  }
}

export function apiError(response, payload, path, method = "GET", autoReport = false) {
  const rawDetail = typeof payload === "string" ? payload : payload?.detail || payload?.error || "";
  const detail = typeof rawDetail === "object" ? rawDetail?.message || "" : rawDetail;
  const deletionId = typeof rawDetail === "object" ? rawDetail?.deletion_id || "" : "";
  const deletionStage = typeof rawDetail === "object" ? rawDetail?.stage || "" : "";
  const status = response?.status || 0;
  let message = GENERIC_MESSAGE;
  if (status === 401) message = "Tu sesión venció. Iniciá sesión nuevamente.";
  else if (status === 402) message = "Esta función necesita una suscripción activa.";
  else if (status === 403) message = detail || "No tenés permiso para realizar esta acción.";
  else if (status === 404) message = detail || "No encontramos la información solicitada.";
  else if (status === 409 || status === 422) message = detail || "Revisá la información e intentá nuevamente.";
  else if (status >= 400 && status < 500) message = detail || "No pudimos procesar la solicitud.";

  const error = new DincrApiError(message, {
    status,
    errorId: deletionId || (typeof payload === "object" ? payload?.error_id : ""),
    requestId: response?.dincrRequestId || response?.headers?.get?.("X-Request-ID") || payload?.request_id || "",
    retryCount: response?.dincrRetryCount || 0,
    path,
    method,
    technicalMessage: deletionStage ? `${detail} [${deletionStage}]` : detail,
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
      summary: "DINCR no pudo completar una acción.",
    };
    window.dispatchEvent(new CustomEvent("dincr:api-error", { detail: incident }));
    captureIncident(incident);
  }
  recordError(error, `api:${path || "unknown"}`);
  return error;
}

export function apiNetworkError(cause, path, method = "GET", autoReport = true) {
  const queued = Boolean(cause?.dincrOperationQueued);
  const error = new DincrApiError(queued
    ? "Guardamos este cambio en el dispositivo. DINCR lo enviará cuando vuelva la conexión."
    : GENERIC_MESSAGE, {
    status: 0,
    errorId: cause?.dincrRequestId || "",
    requestId: cause?.dincrRequestId || "",
    retryCount: cause?.dincrRetryCount || 0,
    path,
    method,
    technicalMessage: cause?.name || "NetworkError",
  });
  error.operationQueued = queued;
  const incident = {
    screen: path, errorReference: error.errorId, requestId: error.requestId,
    retryCount: error.retryCount, status: 0, path, method,
    errorType: cause?.name || "network_error", summary: "DINCR perdió comunicación con el servicio.",
  };
  if (autoReport) {
    window.dispatchEvent(new CustomEvent("dincr:api-error", { detail: incident }));
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
  window.dispatchEvent(new CustomEvent("dincr:open-support", { detail: safeContext }));
}
