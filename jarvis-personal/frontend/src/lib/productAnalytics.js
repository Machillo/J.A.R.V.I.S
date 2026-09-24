import posthog from "posthog-js";
import { Capacitor } from "@capacitor/core";
import { analyticsEvents, safeAnalyticsProperties } from "./analyticsContract";
import { DINCR_APP_ID, isDincrAppId } from "./appIdentity";

const key = import.meta.env.VITE_POSTHOG_KEY?.trim();
const host = import.meta.env.VITE_POSTHOG_HOST?.trim();
const validHost = /^https:\/\/(?:us|eu)\.i\.posthog\.com\/?$/.test(host || "");
const isDincrBuild = isDincrAppId(import.meta.env.VITE_NATIVE_APP_ID || DINCR_APP_ID);

let initialized = false;
let eligible = false;
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
        return { event: event.event, uuid: event.uuid, properties: {
          token: event.properties?.token,
          distinct_id: event.properties?.distinct_id,
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

export const setProductAnalyticsUser = (user) => {
  const plan = user?.subscription?.plan;
  const legalAccepted = user?.legal?.required === false;
  const canTrack = Boolean(user?.id && legalAccepted && user?.role === "user" && ["free", "basic", "vip"].includes(plan));
  if (!canTrack || !initialize()) {
    eligible = false;
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
  context = { plan, platform: Capacitor.getPlatform(), app_version: import.meta.env.VITE_APP_VERSION || "", environment: analyticsEnvironment() };
  eligible = true;
  try { posthog.opt_in_capturing(); } catch { eligible = false; return; }
  if (!opened) {
    opened = true;
    captureProductEvent("app_opened");
  }
  if (loginPending) {
    loginPending = false;
    captureProductEvent("login_completed");
  }
};

// A new sign-in happened; it is reported once the account is eligible (legal
// acceptance, Users plan), so nothing is sent for accounts that never are.
export const noteLoginCompleted = () => { loginPending = true; };

export const captureProductEvent = (name, properties = {}) => {
  if (!eligible || !initialized || !analyticsEvents.has(name)) return;
  try { posthog.capture(name, safeAnalyticsProperties({ ...context, ...properties })); }
  catch { /* optional */ }
};
