import { App as CapacitorApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { supabase } from "./supabase";

export const NATIVE_AUTH_REDIRECT = "com.finva.app://auth/callback";
export const isNativeApp = () => Capacitor.isNativePlatform();

export async function startGoogleLogin() {
  if (!isNativeApp()) {
    return supabase.auth.signInWithOAuth({
      provider: "google",
      options: { queryParams: { prompt: "select_account" } },
    });
  }

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: NATIVE_AUTH_REDIRECT,
      skipBrowserRedirect: true,
      queryParams: { prompt: "select_account" },
    },
  });

  if (error || !data?.url) return { data, error: error || new Error("Google no devolvió una dirección de acceso.") };
  await Browser.open({ url: data.url, presentationStyle: "popover" });
  return { data, error: null };
}

export async function finishNativeLogin(url) {
  if (!url?.startsWith(NATIVE_AUTH_REDIRECT)) return false;

  const parsed = new URL(url);
  const oauthError = parsed.searchParams.get("error_description") || parsed.searchParams.get("error");
  if (oauthError) throw new Error(decodeURIComponent(oauthError));

  const code = parsed.searchParams.get("code");
  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) throw error;
  } else {
    const hash = new URLSearchParams(parsed.hash.replace(/^#/, ""));
    const accessToken = hash.get("access_token");
    const refreshToken = hash.get("refresh_token");
    if (!accessToken || !refreshToken) throw new Error("Google regresó sin una sesión válida.");
    const { error } = await supabase.auth.setSession({ access_token: accessToken, refresh_token: refreshToken });
    if (error) throw error;
  }

  await Browser.close().catch(() => {});
  return true;
}

export async function registerNativeAuthListener(onError) {
  if (!isNativeApp()) return () => {};
  const processUrl = async (url) => {
    try { await finishNativeLogin(url); }
    catch (error) { onError?.(error?.message || "No pudimos completar el acceso con Google."); }
  };
  const listener = await CapacitorApp.addListener("appUrlOpen", ({ url }) => processUrl(url));
  const launch = await CapacitorApp.getLaunchUrl();
  if (launch?.url) await processUrl(launch.url);
  return () => listener.remove();
}
