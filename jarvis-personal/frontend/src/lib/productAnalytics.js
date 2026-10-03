import posthog from "posthog-js";
import { Capacitor } from "@capacitor/core";
import { analyticsEvents, ownerEvents, safeAnalyticsProperties, userEvents } from "./analyticsContract";
import { DINCR_APP_ID, isDincrAppId } from "./appIdentity";

const key = import.meta.env.VITE_POSTHOG_KEY?.trim();
const host = import.meta.env.VITE_POSTHOG_HOST?.trim();
const validHost = /^https:\/\/(?:us|eu)\.i\.posthog\.com\/?$/.test(host || "");
const isDincrBuild = isDincrAppId(import.meta.env.VITE_NATIVE_APP_ID || DINCR_APP_ID);

let initialized = false;
// "user" (Free/Basic/VIP), "owner" (JARVIS metadata only) or null (nothing is sent).
let audience = null;
let context = {};
let opened = false;
let lastUserId = null;
let loginPending = false;

// production / staging / development: explicit build setting, else inferred from the build mode.
export const analyticsEnvironment = () => {
  const configured = String(import.meta.env.VITE_ANALYTICS_ENVIRONMENT || "").trim().toLowerCase();
  if (["production", "staging", "development"].includes(configured)) return configured;
  return import.meta.env.PROD ? "production" : "development";
};

const initialize = () => {
  if (initialized || !isDincrBuild || !Capacitor.isNativePlatform() || !key || !validHost || typeof window === "undefined") return initialized;
  try {
    posthog.init(key, {
      api_host: host,
      autocapture: false,
      capture_pageview: false,
      capture_pageleave: false,
      capture_exceptions: false,
      disable_session_recording: true,
      disable_surveys: true,
      advanced_disable_feature_flags: true,
      disable_external_dependency_loading: true,
      save_campaign_params: false,
      save_referrer: false,
      persistence: "localStorage",
      persistence_name: "dincr_anonymous_analytics_v1",
      opt_out_capturing_by_default: true,
      person_profiles: "never",
      // Retention uses PostHog's anonymous device ID. No account/workspace ID,
      // email, URL, user property or session content leaves the device.
      // posthog-js drops any event whose `token` (the public project key) was
      // removed here, so it is kept. PostHog records the request IP server-side
      // (`ip: false` has no effect): `$geoip_disable` skips IP geolocation.
      before_send: (event) => {
        if (!analyticsEvents.has(event?.event)) return null;
        // $session_id is posthog-js's random per-session UUID (needed to count sessions).
        const sessionId = event.properties?.$session_id;
        return { event: event.event, uuid: event.uuid, properties: {
          token: event.properties?.token,
          distinct_id: event.properties?.distinct_id,
          ...(typeof sessionId === "string" && /^[0-9a-f-]{36}$/i.test(sessionId) ? { $session_id: sessionId } : {}),
          $process_person_profile: false,
          $geoip_disable: true,
          ...safeAnalyticsProperties(event.properties),
        } };
      },
    });
    initialized = true;
  } catch { /* Analytics must never block DINCR. */ }
  return initialized;
};

// Users and the Owner are separate audiences: a Users account sends only Users
// events (audience=user) and the Owner only JARVIS events (audience=owner), so the
// Owner can always be excluded from commercial metrics. Admins are never tracked.
const audienceOf = (user) => {
  if (!user?.id || user?.legal?.required !== false) return null;
  if (user.role === "user" && ["free", "basic", "vip"].includes(user?.subscription?.plan)) return "user";
  if (user.role === "owner") return "owner";
  return null;
};

export const setProductAnalyticsUser = (user) => {
  const nextAudience = audienceOf(user);
  if (!nextAudience || !initialize()) {
    audience = null;
    opened = false;
    lastUserId = null;
    context = {};
    if (initialized) {
      try { posthog.reset(); posthog.opt_out_capturing(); } catch { /* optional */ }
    }
    return;
  }
  if (lastUserId && lastUserId !== user.id) {
    try { posthog.reset(); } catch { /* optional */ }
    opened = false;
  }
  lastUserId = user.id;
  context = {
    audience: nextAudience,
    client: "capacitor",
    ...(nextAudience === "user" ? { plan: user.subscription.plan } : {}),
    platform: Capacitor.getPlatform(),
    app_version: import.meta.env.VITE_APP_VERSION || "",
    environment: analyticsEnvironment(),
  };
  audience = nextAudience;
  try { posthog.opt_in_capturing(); } catch { audience = null; return; }
  if (!opened) {
    opened = true;
    captureProductEvent(audience === "owner" ? "jarvis_opened" : "app_opened");
  }
  if (loginPending) {
    loginPending = false;
    captureProductEvent("login_completed");
  }
};

// A new sign-in happened; it is reported once the account is eligible (legal
// acceptance, Users plan), so nothing is sent for accounts that never are.
export const noteLoginCompleted = () => { loginPending = true; };

const allowedFor = (name) => (audience === "user" ? userEvents : audience === "owner" ? ownerEvents : null)?.has(name);

export const captureProductEvent = (name, properties = {}) => {
  if (!initialized || !analyticsEvents.has(name) || !allowedFor(name)) return;
  // The audience comes from the account, never from the caller.
  try { posthog.capture(name, safeAnalyticsProperties({ ...context, ...properties, audience: context.audience })); }
  catch { /* optional */ }
};
