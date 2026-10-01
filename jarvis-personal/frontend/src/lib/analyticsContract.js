// Analytics observes product behavior, never the user's financial content.
// Fixed categories only: never forward financial data, mail content, OAuth URLs,
// identifiers, free text or form fields. See docs/analytics/posthog-event-taxonomy.md.

// Users (Free, Basic, VIP) events. Canonical names (contract v2); the taxonomy doc
// lists the legacy names they replace. No client event was ever ingested under the
// legacy names, so renaming them loses no history.
export const userEvents = new Set([
  "app_opened", "app_resumed", "screen_viewed", "login_completed", "logout",
  "onboarding_started", "onboarding_completed", "plan_selected", "plan_access_granted",
  "financial_profile_saved", "useful_action", "strategy_tool_opened",
  "mailbox_connection_started", "mailbox_connected", "mailbox_connection_failed",
  "mailbox_disconnected", "mail_sync_requested", "mail_candidate_reviewed",
  "financial_account_reviewed",
  "account_deletion_started", "account_deletion_failed", "data_export_completed",
  "api_error", "app_error",
]);

// Owner (JARVIS) events: internal usage, sent with audience=owner and never mixed
// with Users metrics. Navigation metadata only: never chat text, prompts, calendar
// entries, names, amounts or any personal data.
export const ownerEvents = new Set(["jarvis_opened", "jarvis_section_viewed"]);

export const analyticsEvents = new Set([...userEvents, ...ownerEvents]);

// Mail OAuth outcomes the app can receive; anything else is reported as "other".
export const mailOAuthErrorCodes = new Set([
  "denied", "invalid_state", "expired", "exchange_failed", "vip_required",
  "already_processed", "completion_pending", "completion_failed", "other",
]);

// Every page id of products/finva/features/registry.jsx (checked by the contract test).
export const userScreens = new Set([
  "overview", "finance", "plan", "advisor", "profile", "debts", "strategy", "gmail", "accounts",
  "goals", "savings", "transactions", "situation", "more", "settings", "plan-settings", "budget",
  "calendar", "recurring", "reports", "monthly", "feedback", "vip-recommendation", "vip-projections",
  "vip-projection-detail", "vip-scenarios", "vip-reality", "vip-monthly-review", "vip-today",
  "vip-emergency", "vip-aguinaldo", "vip-preferences",
]);

// Every Owner page of personal/PersonalApp.jsx (checked by the contract test).
export const jarvisSections = new Set([
  "dashboard", "finance", "receivables", "wealth", "reconciliation", "deterioration", "investments",
  "businesses", "goals", "transactions", "memory", "strategy", "emails", "settings", "chats", "profile",
]);

// A useful action is a successful write the user made on purpose: the activation
// and retention signal ("meaningful activity"). Matched on method + API path; the
// path never leaves the device, only the action type.
const usefulActionRules = [
  ["PUT", /^\/user-product\/financial-situation$/, "financial_profile_saved"],
  ["POST", /^\/user-product\/finance\/income$/, "income_added"],
  ["PUT", /^\/user-product\/finance\/income\/[^/]+$/, "income_updated"],
  ["POST", /^\/user-product\/finance\/expenses$/, "expense_added"],
  ["PUT", /^\/user-product\/finance\/expenses\/[^/]+$/, "expense_updated"],
  ["POST", /^\/user-product\/finance\/debts$/, "debt_added"],
  ["PUT", /^\/user-product\/finance\/debts\/[^/]+$/, "debt_updated"],
  ["POST", /^\/user-product\/finance\/debts\/[^/]+\/payments$/, "debt_payment_recorded"],
  ["PUT", /^\/user-product\/vip\/salvavidas$/, "salvavidas_saved"],
  ["POST", /^\/user-product\/goals$/, "goal_created"],
  ["PUT", /^\/user-product\/goals\/[^/]+$/, "goal_updated"],
  ["POST", /^\/user-product\/goals\/[^/]+\/contributions$/, "goal_contribution_recorded"],
  ["POST", /^\/user-product\/savings-plans$/, "savings_plan_created"],
  ["PUT", /^\/user-product\/savings-plans\/[^/]+$/, "savings_plan_updated"],
  ["POST", /^\/user-product\/savings-plans\/[^/]+\/contributions$/, "savings_contribution_recorded"],
  ["POST", /^\/user-product\/transactions$/, "transaction_added"],
  ["PUT", /^\/user-product\/free\/movements\/[^/]+$/, "transaction_updated"],
  ["PUT", /^\/user-product\/basic\/budget$/, "budget_saved"],
  ["POST", /^\/user-product\/basic\/recurring$/, "recurring_added"],
  ["PUT", /^\/user-product\/basic\/recurring\/[^/]+$/, "recurring_updated"],
];
export const usefulActionTypes = new Set([...usefulActionRules.map(([, , type]) => type), "mail_candidate_reviewed"]);

// The action type of a successful Users write, or null when it is not a useful action.
export function usefulActionFor(method, path) {
  const verb = String(method || "").toUpperCase();
  const clean = String(path || "").split(/[?#]/, 1)[0].replace(/\/+$/, "");
  for (const [ruleMethod, pattern, type] of usefulActionRules) if (verb === ruleMethod && pattern.test(clean)) return type;
  return null;
}

// How long a mail candidate waited before review, as a bucket (never a date).
export function reviewLatencyBucket(receivedAt, now = Date.now()) {
  const received = Date.parse(receivedAt || "");
  if (!Number.isFinite(received) || received > now) return undefined;
  const hours = (now - received) / 3_600_000;
  if (hours < 1) return "under_1h";
  if (hours < 24) return "under_1d";
  if (hours < 24 * 7) return "under_7d";
  return "over_7d";
}

const categories = {
  plan: new Set(["free", "basic", "vip"]),
  audience: new Set(["user", "owner"]),
  platform: new Set(["android", "ios"]),
  environment: new Set(["production", "staging", "development"]),
  screen: userScreens,
  jarvis_section: jarvisSections,
  access_type: new Set(["free", "promotion"]),
  plan_change: new Set(["immediate", "scheduled", "kept"]),
  decision: new Set(["accepted", "corrected", "rejected"]),
  review_latency: new Set(["under_1h", "under_1d", "under_7d", "over_7d"]),
  ownership_status: new Set(["own", "not_mine"]),
  provider: new Set(["gmail", "microsoft"]),
  error_code: mailOAuthErrorCodes,
  action_type: usefulActionTypes,
  strategy_tool: new Set(["salvavidas", "investments", "debts", "distribution", "aguinaldo"]),
  // Product module of a failing API call (see endpointModule), never the URL.
  endpoint: new Set(["auth", "home", "transactions", "debts", "goals", "budget", "strategy", "reports", "mail", "accounts", "notifications", "settings", "support", "billing", "other"]),
  method: new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]),
  error_category: new Set(["window_error", "unhandled_rejection", "render_error", "network", "server", "client"]),
};

const booleans = new Set(["success", "is_transfer"]);

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
  ...booleans, ...Object.keys(categories), "app_version", "status_code",
]);

export function safeAnalyticsProperties(properties = {}) {
  const safe = {};
  if (!properties || typeof properties !== "object") return safe;
  for (const [name, value] of Object.entries(properties)) {
    if (booleans.has(name) && typeof value === "boolean") safe[name] = value;
    else if (Object.hasOwn(categories, name) && categories[name].has(value)) safe[name] = value;
    else if (name === "app_version" && typeof value === "string" && /^\d+\.\d+\.\d+$/.test(value)) safe[name] = value;
    else if (name === "status_code" && Number.isInteger(value) && value >= 100 && value <= 599) safe[name] = value;
  }
  return safe;
}
