// Fixed categories only: never forward financial data, OAuth URLs, or form fields.
export const analyticsEvents = new Set([
  "app_opened", "app_resumed", "screen_viewed", "onboarding_started",
  "onboarding_completed", "plan_selected", "plan_access_granted",
  "gmail_connection_started", "gmail_connected", "mail_connected", "gmail_sync_started",
  "gmail_sync_completed", "gmail_sync_failed", "gmail_disconnected",
  "financial_account_detected", "financial_account_confirmed",
  "financial_account_ownership_reviewed", "email_candidate_reviewed", "transaction_candidate_reviewed",
  "transaction_confirmed", "transaction_rejected", "account_deletion_started",
  "account_deletion_failed",
]);

const categories = {
  plan: new Set(["free", "basic", "vip"]),
  platform: new Set(["android", "ios"]),
  screen: new Set(["overview", "finance", "debts", "goals", "transactions", "strategy", "gmail", "budget", "calendar", "recurring", "reports", "settings", "feedback"]),
  access_type: new Set(["free", "promotion"]),
  source_type: new Set(["email", "manual"]),
  decision: new Set(["accepted", "corrected", "rejected"]),
  ownership_status: new Set(["own", "not_mine"]),
  scan_scope: new Set(["recent", "year_to_date"]),
};

const booleans = new Set(["success", "initial_scan_complete"]);

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
  }
  return safe;
}
