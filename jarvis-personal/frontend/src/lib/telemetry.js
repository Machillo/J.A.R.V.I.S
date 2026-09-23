import { Capacitor } from "@capacitor/core";
import { FirebaseAnalytics } from "@capacitor-firebase/analytics";
import { FirebaseCrashlytics } from "@capacitor-firebase/crashlytics";
import { captureProductEvent, setProductAnalyticsUser } from "./productAnalytics";

const native = Capacitor.isNativePlatform();
const safely = (action) => native ? Promise.resolve().then(action).catch(() => {}) : Promise.resolve();

export const initializeTelemetry = () => {
  if (!native) return () => {};
  const onError = (event) => recordError(event.error || new Error(event.message || "Unhandled JavaScript error"), "window_error");
  const onRejection = (event) => recordError(event.reason instanceof Error ? event.reason : new Error(String(event.reason || "Unhandled promise rejection")), "unhandled_rejection");
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  safely(() => FirebaseCrashlytics.log({ message: "app_started" }));
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
};

export const identifyTelemetryUser = (user) => {
  const userId = user?.id ? String(user.id) : null;
  const plan = String(user?.subscription?.plan || user?.plan || "unknown").slice(0, 24);
  safely(() => FirebaseAnalytics.setUserId({ userId }));
  safely(() => FirebaseAnalytics.setUserProperty({ key: "plan", value: plan }));
  safely(() => FirebaseCrashlytics.setUserId({ userId: userId || "anonymous" }));
  safely(() => FirebaseCrashlytics.setCustomKey({ key: "plan", value: plan, type: "string" }));
  setProductAnalyticsUser(user);
};

export const trackScreen = (screenName, surface = "unknown") => {
  const cleanScreen = String(screenName || "unknown").slice(0, 80);
  const cleanSurface = String(surface || "unknown").slice(0, 40);
  window.sessionStorage.setItem("finva:current-screen", cleanScreen);
  safely(() => FirebaseAnalytics.setCurrentScreen({ screenName: cleanScreen, screenClassOverride: cleanSurface }));
  safely(() => FirebaseCrashlytics.setCustomKey({ key: "screen", value: cleanScreen, type: "string" }));
  safely(() => FirebaseCrashlytics.log({ message: `screen:${cleanScreen}` }));
  captureProductEvent("screen_viewed", { screen: cleanScreen.replace(/^finva_/, "") });
};

export const trackEvent = (name, params = {}) => {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 20)
  );
  safely(() => FirebaseAnalytics.logEvent({ name: String(name).slice(0, 40), params: cleanParams }));
  captureProductEvent(name, cleanParams);
};

export const recordError = (error, context = "handled") => {
  const message = error instanceof Error ? error.message : String(error || "Unknown error");
  safely(() => FirebaseCrashlytics.log({ message: `error_context:${String(context).slice(0, 80)}` }));
  safely(() => FirebaseCrashlytics.recordException({ message: message.slice(0, 500) }));
};
