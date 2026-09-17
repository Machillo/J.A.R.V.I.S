import { supabase } from "./supabase";

const SESSION_EXPIRED_MESSAGE = "Tu sesión venció. Iniciá sesión nuevamente.";
const REQUEST_TIMEOUT_MS = 20_000;

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
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`,
      },
    });
  } catch (error) {
    if (controller.signal.aborted && !upstreamSignal?.aborted) {
      throw new Error("La solicitud tardó demasiado. Volvé a intentarlo.", { cause: error });
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    upstreamSignal?.removeEventListener?.("abort", abortFromUpstream);
  }
}

export async function authenticatedFetch(url, options = {}) {
  let response = await withToken(url, options, await activeToken());
  if (response.status !== 401) return response;

  response = await withToken(url, options, await activeToken(true));
  if (response.status === 401) {
    await supabase.auth.signOut({ scope: "local" }).catch(() => {});
    throw new Error(SESSION_EXPIRED_MESSAGE);
  }

  return response;
}
