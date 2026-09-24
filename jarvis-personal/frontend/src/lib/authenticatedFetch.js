import { supabase } from "./supabase";
import { deviceLanguage, tx } from "./locale";

const SESSION_EXPIRED_MESSAGE = tx("Tu sesión venció. Iniciá sesión nuevamente.", "Your session expired. Please sign in again.");
const REQUEST_TIMEOUT_MS = 20_000;
const RETRYABLE_STATUS = new Set([408, 425, 429, 502, 503, 504]);
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

const newRequestId = () => globalThis.crypto?.randomUUID?.()
  || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

const delay = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

async function activeToken(forceRefresh = false) {
  const result = forceRefresh
    ? await supabase.auth.refreshSession()
    : await supabase.auth.getSession();
  const session = result?.data?.session;

  if (result?.error || !session?.access_token) {
    await supabase.auth.signOut({ scope: "local" }).catch(() => {});
    throw new Error(SESSION_EXPIRED_MESSAGE);
  }

  return session.access_token;
}

async function withToken(url, options, token) {
  const controller = new AbortController();
  const upstreamSignal = options.signal;
  const abortFromUpstream = () => controller.abort(upstreamSignal?.reason);
  if (upstreamSignal) {
    if (upstreamSignal.aborted) abortFromUpstream();
    else upstreamSignal.addEventListener("abort", abortFromUpstream, { once: true });
  }

  const timeout = window.setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    REQUEST_TIMEOUT_MS,
  );
  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        // The backend writes its narrative text in the same language as the UI.
        "Accept-Language": deviceLanguage(),
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`,
      },
    });
  } catch (error) {
    if (controller.signal.aborted && !upstreamSignal?.aborted) {
      throw new Error(tx("La solicitud tardó demasiado. Volvé a intentarlo.", "The request took too long. Please try again."), { cause: error });
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    upstreamSignal?.removeEventListener?.("abort", abortFromUpstream);
  }
}

export async function authenticatedFetch(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const requestId = options.headers?.["X-Request-ID"] || newRequestId();
  const safeToRetry = SAFE_METHODS.has(method);
  const maxRetries = safeToRetry ? 2 : 0;
  let retryCount = 0;
  let refreshed = false;
  let token = await activeToken();

  while (true) {
    const requestOptions = {
      ...options,
      headers: {
        ...(options.headers || {}),
        "X-Request-ID": requestId,
        "X-Retry-Attempt": String(retryCount),
      },
    };
    try {
      let response = await withToken(url, requestOptions, token);
      if (response.status === 401 && !refreshed) {
        refreshed = true;
        token = await activeToken(true);
        response = await withToken(url, requestOptions, token);
      }
      if (response.status === 401) {
        await supabase.auth.signOut({ scope: "local" }).catch(() => {});
        throw new Error(SESSION_EXPIRED_MESSAGE);
      }
      if (safeToRetry && RETRYABLE_STATUS.has(response.status) && retryCount < maxRetries) {
        retryCount += 1;
        await delay(retryCount === 1 ? 250 : 750);
        continue;
      }
      response.finvaRequestId = response.headers.get("X-Request-ID") || requestId;
      response.finvaRetryCount = retryCount;
      return response;
    } catch (error) {
      if (error?.message === SESSION_EXPIRED_MESSAGE) throw error;
      if (!safeToRetry || retryCount >= maxRetries) {
        error.finvaRequestId = requestId;
        error.finvaRetryCount = retryCount;
        throw error;
      }
      retryCount += 1;
      await delay(retryCount === 1 ? 250 : 750);
    }
  }
}
