import { supabase } from "./supabase";

const SESSION_EXPIRED_MESSAGE = "Tu sesión venció. Iniciá sesión nuevamente.";

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
  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });
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
