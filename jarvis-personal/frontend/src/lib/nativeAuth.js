import { App as CapacitorApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { supabase } from "./supabase";
import { nativeAppId } from "./appIdentity";
import { tx } from "./locale";

const signInFailed = () => tx("No pudimos completar el acceso. Intentá nuevamente.", "We couldn’t sign you in. Please try again.");

export const NATIVE_AUTH_REDIRECT = `${nativeAppId}://auth/callback`;
export const isNativeApp = () => Capacitor.isNativePlatform();

const PROVIDER_OPTIONS = {
  google: { queryParams: { prompt: "select_account" } },
  apple: { scopes: "name email" },
};

export async function startOAuthLogin(provider) {
  const providerOptions = PROVIDER_OPTIONS[provider] || {};
  if (!isNativeApp()) {
    return supabase.auth.signInWithOAuth({ provider, options: providerOptions });
  }

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: { ...providerOptions, redirectTo: NATIVE_AUTH_REDIRECT, skipBrowserRedirect: true },
  });

  if (error || !data?.url) return { data, error: new Error(signInFailed()) };
  await Browser.open({ url: data.url, presentationStyle: "popover" });
  return { data, error: null };
}

export async function finishNativeLogin(url) {
  if (!url?.startsWith(NATIVE_AUTH_REDIRECT)) return false;

  const parsed = new URL(url);
  const oauthError = parsed.searchParams.get("error_description") || parsed.searchParams.get("error");
  if (oauthError) throw new Error(decodeURIComponent(oauthError));

  // Only accept the PKCE code: its verifier lives on this device, so a crafted
  // deep link cannot inject someone else's session tokens.
  const code = parsed.searchParams.get("code");
  if (!code) throw new Error(signInFailed());
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) throw error;

  await Browser.close().catch(() => {});
  return true;
}

export async function registerNativeAuthListener(onError) {
  if (!isNativeApp()) return () => {};
  const processUrl = async (url) => {
    try { await finishNativeLogin(url); }
    catch { onError?.(signInFailed()); }
  };
  const listener = await CapacitorApp.addListener("appUrlOpen", ({ url }) => processUrl(url));
  const launch = await CapacitorApp.getLaunchUrl();
  if (launch?.url) await processUrl(launch.url);
  return () => listener.remove();
}
