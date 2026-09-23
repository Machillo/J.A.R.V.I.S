import posthog from "posthog-js";
import { Capacitor } from "@capacitor/core";

const key = import.meta.env.VITE_POSTHOG_KEY;
const host = import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com";

const allowedEvents = new Set([
  "app_resumed",
  "screen_viewed",
  "gmail_connection_started",
  "gmail_sync_completed",
  "gmail_disconnected",
  "email_candidate_reviewed",
  "financial_account_ownership_reviewed",
  "plan_access_granted",
]);

const allowedProperties = new Set([
  "screen",
  "surface",
  "plan",
  "platform",
  "app_version",
  "decision",
  "bank",
  "institution_country",
  "source_type",
  "is_internal_transfer",
  "scan_scope",
  "initial_scan_complete",
  "auto_saved_bucket",
  "pending_bucket",
  "ownership_status",
  "access_type",
]);

let initialized = false;
let eligible = false;
let context = {};

const cleanString = (value, max = 64) => String(value || "unknown")
  .trim()
  .toLowerCase()
  .replace(/[^a-z0-9_.-]/g, "_")
  .slice(0, max) || "unknown";

const countBucket = (value) => {
  const count = Math.max(0, Number(value) || 0);
  if (count === 0) return "0";
  if (count === 1) return "1";
  if (count <= 5) return "2_5";
  if (count <= 20) return "6_20";
  return "21_plus";
};

const initialize = () => {
  if (initialized || !key || typeof window === "undefined") return Boolean(initialized);
  posthog.init(key, {
    api_host: host,
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    disable_session_recording: true,
    disable_surveys: true,
    opt_out_capturing_by_default: true,
    persistence: "localStorage+cookie",
    person_profiles: "identified_only",
    sanitize_properties: (properties) => {
      const safe = {};
      Object.entries(properties || {}).forEach(([name, value]) => {
        if (name.startsWith("$") || allowedProperties.has(name)) safe[name] = value;
      });
      return safe;
    },
  });
  initialized = true;
  return true;
};

export const setProductAnalyticsUser = (user) => {
  const userId = user?.id ? String(user.id) : "";
  const role = String(user?.role || "user").toLowerCase();
  const legalAccepted = Boolean(user && !user?.legal?.required);
  eligible = Boolean(userId && legalAccepted && role !== "owner" && role !== "admin");

  if (!eligible) {
    context = {};
    if (initialized) {
      posthog.reset();
      posthog.opt_out_capturing();
    }
    return;
  }

  if (!initialize()) return;
  const plan = cleanString(user?.subscription?.plan || user?.plan || "unknown", 24);
  const platform = cleanString(Capacitor.getPlatform(), 16);
  context = { plan, platform };
  posthog.opt_in_capturing();
  posthog.identify(userId, { plan, platform, product: "dincr" });
};

export const captureProductEvent = (eventName, properties = {}) => {
  const event = String(eventName || "");
  if (!eligible || !initialized || !allowedEvents.has(event)) return;
  const safe = { ...context };
  Object.entries(properties || {}).forEach(([name, value]) => {
    if (!allowedProperties.has(name)) return;
    if (name === "auto_saved" || name === "pending") return;
    if (["is_internal_transfer", "initial_scan_complete"].includes(name)) safe[name] = Boolean(value);
    else safe[name] = cleanString(value);
  });
  if (Object.hasOwn(properties, "auto_saved")) safe.auto_saved_bucket = countBucket(properties.auto_saved);
  if (Object.hasOwn(properties, "pending")) safe.pending_bucket = countBucket(properties.pending);
  posthog.capture(event, safe);
};

export const productAnalyticsContract = { allowedEvents, allowedProperties, countBucket };
