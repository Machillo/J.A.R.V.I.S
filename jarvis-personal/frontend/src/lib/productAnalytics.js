import posthog from "posthog-js";
import { Capacitor } from "@capacitor/core";
import { analyticsEvents, safeAnalyticsProperties } from "./analyticsContract";
import { LEGACY_DINCR_APP_ID, isDincrAppId } from "./appIdentity";

const key = import.meta.env.VITE_POSTHOG_KEY?.trim();
const host = import.meta.env.VITE_POSTHOG_HOST?.trim();
const validHost = /^https:\/\/(?:us|eu)\.i\.posthog\.com\/?$/.test(host || "");
const isDincrBuild = isDincrAppId(import.meta.env.VITE_NATIVE_APP_ID || LEGACY_DINCR_APP_ID);

let initialized = false;
let eligible = false;
let context = {};
let opened = false;
let lastUserId = null;

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
      ip: false,
      persistence: "localStorage",
      persistence_name: "dincr_anonymous_analytics_v1",
      opt_out_capturing_by_default: true,
      person_profiles: "never",
      // Retention uses PostHog's anonymous device ID. No account/workspace ID,
      // email, URL, user property or session content leaves the device.
      before_send: (event) => {
        if (!analyticsEvents.has(event?.event)) return null;
        return { event: event.event, uuid: event.uuid, properties: {
          distinct_id: event.properties?.distinct_id,
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
  context = { plan, platform: Capacitor.getPlatform(), app_version: import.meta.env.VITE_APP_VERSION || "" };
  eligible = true;
  try { posthog.opt_in_capturing(); } catch { eligible = false; return; }
  if (!opened) {
    opened = true;
    captureProductEvent("app_opened");
  }
};

export const captureProductEvent = (name, properties = {}) => {
  if (!eligible || !initialized || !analyticsEvents.has(name)) return;
  try { posthog.capture(name, safeAnalyticsProperties({ ...context, ...properties })); }
  catch { /* optional */ }
};
