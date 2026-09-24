import { Capacitor } from "@capacitor/core";
import { captureProductEvent, setProductAnalyticsUser } from "./productAnalytics";

// DINCR telemetry facade. PostHog (productAnalytics.js + analyticsContract.js) is
// the only analytics/observability system: it receives fixed event names and
// closed-list properties, never messages, stacks, paths, identities or financial
// data. Firebase is used only to distribute test builds and must not observe
// users: no Firebase SDK is called from here or anywhere in the app runtime.

const native = Capacitor.isNativePlatform();

export const initializeTelemetry = () => {
  if (!native) return () => {};
  // Only the category of an unhandled error is reported, never its message or stack.
  const onError = () => captureProductEvent("app_error", { error_category: "window_error" });
  const onRejection = () => captureProductEvent("app_error", { error_category: "unhandled_rejection" });
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
};

export const identifyTelemetryUser = (user) => {
  setProductAnalyticsUser(user);
};

export const trackScreen = (screenName) => {
  const cleanScreen = String(screenName || "unknown").slice(0, 80);
  // Local only: the incident reporter labels a failure with the screen it happened on.
  window.sessionStorage.setItem("finva:current-screen", cleanScreen);
  captureProductEvent("screen_viewed", { screen: cleanScreen.replace(/^finva_/, "") });
};

export const trackEvent = (name, params = {}) => {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 20)
  );
  captureProductEvent(name, cleanParams);
};

// A React render failure is reported as a category only. API failures are already
// reported (deduplicated) as `api_error` by the incident reporter, so they are not
// repeated here; the error object itself never leaves the device.
export const recordError = (_error, context = "handled") => {
  if (String(context).startsWith("react:")) captureProductEvent("app_error", { error_category: "render_error" });
};
