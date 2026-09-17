import { recordError } from "./telemetry";

export const SUPPORT_CONTEXT_KEY = "finva:support-context";

const GENERIC_MESSAGE = "No pudimos completar esta acción. Intentá nuevamente o pedí ayuda a soporte.";

export class FinvaApiError extends Error {
  constructor(message, { status, errorId, path, technicalMessage } = {}) {
    super(message);
    this.name = "FinvaApiError";
    this.status = status;
    this.errorId = errorId || "";
    this.path = path || "";
    this.technicalMessage = technicalMessage || "";
  }
}

export function apiError(response, payload, path) {
  const detail = typeof payload === "string" ? payload : payload?.detail || payload?.error || "";
  const status = response?.status || 0;
  let message = GENERIC_MESSAGE;
  if (status === 401) message = "Tu sesión venció. Iniciá sesión nuevamente.";
  else if (status === 402) message = "Esta función necesita una suscripción activa.";
  else if (status === 403) message = detail || "No tenés permiso para realizar esta acción.";
  else if (status === 404) message = detail || "No encontramos la información solicitada.";
  else if (status === 409 || status === 422) message = detail || "Revisá la información e intentá nuevamente.";
  else if (status >= 400 && status < 500) message = detail || "No pudimos procesar la solicitud.";

  const error = new FinvaApiError(message, {
    status,
    errorId: typeof payload === "object" ? payload?.error_id : "",
    path,
    technicalMessage: detail,
  });
  if (status >= 500 || status === 0) {
    window.dispatchEvent(new CustomEvent("finva:api-error", { detail: {
      screen: path,
      errorReference: error.errorId,
      summary: "FINVA no pudo completar una acción.",
    } }));
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
