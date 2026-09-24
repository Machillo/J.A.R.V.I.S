// Analytics observes product behavior, never the user's financial content.
// Fixed categories only: never forward financial data, mail content, OAuth URLs,
// identifiers or form fields. See docs/analytics/posthog-event-taxonomy.md.
export const analyticsEvents = new Set([
  "app_opened", "app_resumed", "screen_viewed", "onboarding_started",
  "onboarding_completed", "plan_selected", "plan_access_granted",
  "login_completed", "logout",
  "gmail_connection_started", "gmail_connected", "mail_connected", "mailbox_connection_failed",
  "gmail_sync_started", "gmail_sync_completed", "gmail_sync_failed", "gmail_disconnected",
  "financial_account_detected", "financial_account_confirmed",
  "financial_account_ownership_reviewed", "email_candidate_reviewed", "transaction_candidate_reviewed",
  "transaction_confirmed", "transaction_rejected", "account_deletion_started",
  "account_deletion_failed", "data_export_completed",
  "api_error", "app_error",
]);

// Mail OAuth outcomes the app can receive; anything else is reported as "other".
export const mailOAuthErrorCodes = new Set([
  "denied", "invalid_state", "expired", "exchange_failed", "vip_required",
  "already_processed", "completion_pending", "completion_failed", "other",
]);

const categories = {
  plan: new Set(["free", "basic", "vip"]),
  platform: new Set(["android", "ios"]),
  environment: new Set(["production", "staging", "development"]),
  // Every page id registered in products/finva/features/registry.jsx.
  screen: new Set(["overview", "finance", "debts", "goals", "transactions", "strategy", "gmail", "accounts", "budget", "calendar", "recurring", "reports", "settings", "feedback", "advisor", "monthly", "more", "plan", "profile", "savings", "situation"]),
  access_type: new Set(["free", "promotion"]),
  source_type: new Set(["email", "manual"]),
  decision: new Set(["accepted", "corrected", "rejected"]),
  ownership_status: new Set(["own", "not_mine"]),
  scan_scope: new Set(["recent", "year_to_date", "current_month", "current_year"]),
  provider: new Set(["gmail", "microsoft"]),
  error_code: mailOAuthErrorCodes,
  // Product module of a failing API call (see endpointModule), never the URL.
  endpoint: new Set(["auth", "home", "transactions", "debts", "goals", "budget", "strategy", "reports", "mail", "accounts", "notifications", "settings", "support", "billing", "other"]),
  method: new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]),
  error_category: new Set(["window_error", "unhandled_rejection", "network", "server", "client"]),
};

const booleans = new Set(["success", "initial_scan_complete"]);
// Aggregate message counts of a mail sync: how many, never which or what.
const counts = new Set(["messages_scanned", "candidates_pending", "duplicates"]);

const endpointRules = [
  [/^\/auth\b/, "auth"],
  [/^\/user-product\/vip\/(gmail|mail)\b/, "mail"],
  [/^\/user-product\/vip\/(financial-identity|accounts)\b|\/accounts\b/, "accounts"],
  [/strategy/, "strategy"],
  [/debt/, "debts"],
  [/goal/, "goals"],
  [/budget/, "budget"],
  [/report|monthly-review/, "reports"],
  [/movement|transaction/, "transactions"],
  [/notification/, "notifications"],
  [/feedback|support|incident/, "support"],
  [/billing|checkout|plan/, "billing"],
  [/dashboard|command-center|lifecycle|situation|overview/, "home"],
  [/settings|profile|preferences/, "settings"],
];

// Map an API path to a fixed product module. The path itself never leaves the device.
export function endpointModule(path) {
  const clean = String(path || "").split(/[?#]/, 1)[0].toLowerCase();
  for (const [pattern, module] of endpointRules) if (pattern.test(clean)) return module;
  return "other";
}

// Every property name that can ever leave the device (checked by the privacy guard test).
export const analyticsPropertyNames = new Set([
  ...booleans, ...Object.keys(categories), ...counts, "app_version", "duration_ms", "status_code",
]);

export function safeAnalyticsProperties(properties = {}) {
  const safe = {};
  if (!properties || typeof properties !== "object") return safe;
  for (const [name, value] of Object.entries(properties)) {
    if (booleans.has(name) && typeof value === "boolean") safe[name] = value;
    else if (categories[name]?.has(value)) safe[name] = value;
    else if (name === "app_version" && typeof value === "string" && /^\d+\.\d+\.\d+$/.test(value)) safe[name] = value;
    else if (name === "duration_ms" && Number.isFinite(value) && value >= 0) {
      safe.duration_ms = Math.min(60_000, Math.round(value / 1000) * 1000);
    }
    else if (counts.has(name) && Number.isInteger(value) && value >= 0) safe[name] = Math.min(value, 100_000);
    else if (name === "status_code" && Number.isInteger(value) && value >= 100 && value <= 599) safe[name] = value;
  }
  return safe;
}
