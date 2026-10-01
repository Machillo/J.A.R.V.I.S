import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { analyticsEvents, analyticsPropertyNames, endpointModule, jarvisSections, mailOAuthErrorCodes, ownerEvents, reviewLatencyBucket, safeAnalyticsProperties, usefulActionFor, userEvents, userScreens } from "../src/lib/analyticsContract.js";
import { DINCR_APP_ID, isDincrAppId } from "../src/lib/appIdentity.js";

const sdk = fs.readFileSync(new URL("../src/lib/productAnalytics.js", import.meta.url), "utf8");
const gmail = fs.readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");

assert.deepEqual(safeAnalyticsProperties({
  plan: "vip", platform: "android", success: true, decision: "corrected",
  bank: "Banco de mi papá", account: "1234", amount: 5000,
  balance: 7000, debt: 8000, email: "private@example.com", subject: "pago",
  sender: "bank@example.com", description: "salary", token: "private", pdf: "%PDF",
  $current_url: "https://example.com/#access_token=secret", $set: { email: "private@example.com" },
}), { plan: "vip", platform: "android", success: true, decision: "corrected" });
assert.deepEqual(safeAnalyticsProperties({ plan: "VIP@gmail.com", platform: "web", source_type: "BAC", screen: "/debts/1234" }), {});
assert.deepEqual(safeAnalyticsProperties({ app_version: "1.9.11", success: false, is_transfer: true, constructor: "x", toString: "y" }), {
  app_version: "1.9.11", success: false,
});
assert.ok(analyticsEvents.has("account_deletion_started"));
assert.equal(analyticsEvents.has("$pageview"), false);
assert.match(sdk, /autocapture: false/);
assert.match(sdk, /capture_pageview: false/);
assert.match(sdk, /disable_session_recording: true/);
assert.match(sdk, /capture_exceptions: false/);
assert.match(sdk, /person_profiles: "never"/);
assert.match(sdk, /before_send:/);
assert.match(sdk, /user\?\.legal\?\.required !== false\) return null/);
assert.doesNotMatch(sdk, /posthog\.identify\(/);
assert.doesNotMatch(gmail, /bank: item\.|institution_country: item\.|auto_saved: result\./);
assert.match(gmail, /trackEvent\("mailbox_connected", \{ provider: outcome\.provider \}\)/, "every provider's connection is counted on the device");
assert.match(gmail, /review_latency: reviewLatencyBucket\(item\.created_at\) \}/, "review latency: a bucket of DINCR's detection time, nothing from the email");
const reviewEvent = gmail.slice(gmail.indexOf('trackEvent("mail_candidate_reviewed"'), gmail.indexOf('trackEvent("useful_action"'));
assert.ok(reviewEvent.length > 0 && !/received_at|is_internal_transfer|is_transfer|bank|subject|sender/.test(reviewEvent), "no value derived from the email is sent with a review");

function runSdk({ key = "", mobile = true, legal = false, appId = "com.dincr.app", role = "user", plan = "vip" } = {}) {
  const calls = [];
  const sdkStub = {
    init: (_token, config) => { calls.push(["init", config]); sdkStub.config = config; },
    capture: (event, props) => { calls.push(["capture", sdkStub.config.before_send({ event, uuid: "random-uuid", properties: { ...props, token: "phc_public_project_key", distinct_id: "random-device-id", $process_person_profile: true, $current_url: "https://x/#token=private", $set: { email: "private@example.com" } } })]); },
    opt_in_capturing: () => calls.push(["opt_in"]),
    opt_out_capturing: () => calls.push(["opt_out"]),
    reset: () => calls.push(["reset"]),
  };
  const source = sdk.replace(/^import .*;\r?\n/gm, "").replaceAll("import.meta.env", "env").replace(/export const /g, "const ");
  const context = {
    posthog: sdkStub, analyticsEvents, userEvents, ownerEvents, safeAnalyticsProperties, DINCR_APP_ID, isDincrAppId,
    Capacitor: { isNativePlatform: () => mobile, getPlatform: () => "android" },
    env: { VITE_POSTHOG_KEY: key, VITE_POSTHOG_HOST: "https://us.i.posthog.com", VITE_NATIVE_APP_ID: appId },
    window: {},
  };
  vm.runInNewContext(`${source}\nglobalThis.run = { setProductAnalyticsUser, captureProductEvent, noteLoginCompleted };`, context);
  context.posthogConfig = () => sdkStub.config;
  context.run.setProductAnalyticsUser({ id: "account-id", role, legal: { required: !legal }, subscription: { plan } });
  return { calls, context };
}

assert.deepEqual(runSdk().calls, [], "missing key is a no-op");
assert.deepEqual(runSdk({ key: "public-key" }).calls, [], "missing legal acceptance is a no-op");
assert.deepEqual(runSdk({ key: "public-key", legal: true, mobile: false }).calls, [], "Vercel preview is excluded");
assert.ok(runSdk({ key: "public-key", legal: true, appId: "com.dincr.app" }).calls.length, "the DINCR iOS build (com.dincr.app) keeps product analytics");
assert.deepEqual(runSdk({ key: "public-key", legal: true, appId: "com.jarvis.personal" }).calls, [], "a non-DINCR build never sends analytics");
const { calls, context } = runSdk({ key: "public-key", legal: true });
assert.deepEqual(calls.filter(([name]) => name === "capture").map(([, event]) => event.event), ["app_opened"]);
context.run.captureProductEvent("mail_candidate_reviewed", { amount: 1234, bank: "BAC", decision: "accepted", audience: "owner" });
const event = calls.at(-1)[1];
assert.deepEqual(Object.keys(event).sort(), ["event", "properties", "uuid"]);
assert.equal(event.properties.amount, undefined);
assert.equal(event.properties.$current_url, undefined);
assert.equal(event.properties.$set, undefined);
assert.equal(event.properties.email, undefined);
assert.equal(event.properties.decision, "accepted");
assert.equal(event.properties.audience, "user", "the caller can never change the audience");
assert.equal(event.properties.token, "phc_public_project_key", "the public project key is required for ingestion");
assert.equal(event.properties.$process_person_profile, false, "no person profiles");
assert.equal(event.properties.$geoip_disable, true, "no IP geolocation");
assert.deepEqual(Object.keys(event.properties).sort(), ["$geoip_disable", "$process_person_profile", "audience", "decision", "distinct_id", "environment", "plan", "platform", "token"]);
assert.equal(event.properties.environment, "development", "non-production builds are labelled");

// The real posthog-js pipeline must accept what before_send returns. It silently
// drops events whose required properties (`token`) were removed by the hook.
const { PostHog } = createRequire(import.meta.url)("posthog-js/lib/src/posthog-core.js");
const realSdk = new PostHog();
realSdk.config = { before_send: context.posthogConfig().before_send };
const ingested = realSdk._runBeforeSend({ event: "app_opened", uuid: "u", properties: { token: "phc_public_project_key", distinct_id: "d", $lib: "web", $current_url: "https://x/#access_token=secret", plan: "vip" } });
assert.ok(ingested, "posthog-js keeps DINCR events after before_send");
assert.deepEqual(JSON.parse(JSON.stringify(ingested.properties)), { token: "phc_public_project_key", distinct_id: "d", $process_person_profile: false, $geoip_disable: true, plan: "vip" });
assert.equal(realSdk._runBeforeSend({ event: "$pageview", uuid: "u", properties: { token: "t", distinct_id: "d" } }), null, "unlisted events stay dropped");
const sessionUuid = "0192f0c4-7b1a-7c3e-9a51-3f2b8d6e1a90";
assert.equal(realSdk._runBeforeSend({ event: "app_opened", uuid: "u", properties: { token: "t", distinct_id: "d", $session_id: sessionUuid } }).properties.$session_id, sessionUuid, "the random session id is kept to count sessions");
assert.equal(realSdk._runBeforeSend({ event: "app_opened", uuid: "u", properties: { token: "t", distinct_id: "d", $session_id: "ana@example.com" } }).properties.$session_id, undefined, "anything that is not a UUID is dropped");
context.run.captureProductEvent("unapproved_event", { decision: "accepted" });
context.run.captureProductEvent("jarvis_section_viewed", { jarvis_section: "chats" });
assert.equal(calls.filter(([name]) => name === "capture").length, 2, "Users accounts never send Owner events");
context.run.setProductAnalyticsUser({ id: "second-account", role: "user", legal: { required: false }, subscription: { plan: "free" } });
assert.ok(calls.some(([name]) => name === "reset"), "switching accounts must rotate the anonymous ID");
assert.equal(calls.filter(([name, value]) => name === "capture" && value.event === "app_opened").length, 2);

// --- Privacy guard: no allowed property name may describe financial content,
// mail content, identity or credentials. Adding one to the contract fails here.
const SENSITIVE = /amount|balance|salary|income|debt|iban|account_?(id|number)|workspace|card|sinpe|subject|body|snippet|sender|recipient|counterpart|payee|payer|email|mail_?address|name|token|secret|password|cookie|auth|header|raw|payload|description|merchant|url|path|query|stack|(^|_)message($|_)|(^|_)ip($|_)|phone|user_?id|person|prompt|(^|_)text($|_)|chat|conversation|transcript|calendar|title|note|content|(^|_)date|(^|_)at$|address|location|wealth/i;
for (const name of analyticsPropertyNames) assert.doesNotMatch(name, SENSITIVE, `analytics property '${name}' looks sensitive`);
const hostile = {
  amount: 12500, balance: 1, salary: 1, debt: 1, iban: "CR05015202001026284066", account_number: "1234",
  card: "4111111111111111", sinpe: "88888888", subject: "Pago", body: "Hola", snippet: "Compra", sender: "banco@x.com",
  counterparty: "Persona", email: "a@b.com", name: "Persona", access_token: "t", refresh_token: "t",
  authorization: "Bearer x", cookie: "c", password: "p", raw_payload: { amount: 1 }, description: "x",
  account_id: "uuid", workspace_id: "uuid", user_id: 1, $current_url: "https://x", $set: { email: "a@b.com" },
  endpoint: "/user-product/vip/gmail/42", status_code: "500", provider: "yahoo",
  prompt: "cuanto gane", text: "hola", chat_message: "x", calendar_title: "Cita", received_at: "2026-09-30",
  jarvis_section: "chat: pagar a Ana", action_type: "transfer 5000", review_latency: "3h", strategy_tool: "x", audience: "admin",
};
assert.deepEqual(safeAnalyticsProperties(hostile), {}, "hostile or malformed values never pass");

// --- Closed categories.
assert.deepEqual(safeAnalyticsProperties({ provider: "microsoft", error_code: "denied", status_code: 503, endpoint: "mail", method: "POST", error_category: "server", environment: "production", audience: "owner", jarvis_section: "chats", action_type: "goal_created", review_latency: "under_1d", strategy_tool: "aguinaldo", plan_change: "scheduled" }),
  { provider: "microsoft", error_code: "denied", status_code: 503, endpoint: "mail", method: "POST", error_category: "server", environment: "production", audience: "owner", jarvis_section: "chats", action_type: "goal_created", review_latency: "under_1d", strategy_tool: "aguinaldo", plan_change: "scheduled" });

// --- Useful actions: a successful write, identified by method + path; the path never leaves.
for (const [method, path, type] of [
  ["PUT", "/user-product/financial-situation", "financial_profile_saved"], ["POST", "/user-product/goals", "goal_created"],
  ["POST", "/user-product/goals/12/contributions", "goal_contribution_recorded"], ["POST", "/user-product/finance/debts/9/payments", "debt_payment_recorded"],
  ["PUT", "/user-product/vip/salvavidas", "salvavidas_saved"], ["POST", "/user-product/transactions?x=1", "transaction_added"],
  ["GET", "/user-product/goals", null], ["POST", "/user-product/finance/strategy-vip/simulate", null], ["POST", "/user-product/vip/gmail/connect", null],
  ["DELETE", "/user-product/goals/12", null], ["POST", "/product-ops/events", null],
]) assert.equal(usefulActionFor(method, path), type, `${method} ${path}`);
const now = Date.parse("2026-10-01T12:00:00Z");
assert.equal(reviewLatencyBucket("2026-10-01T11:30:00Z", now), "under_1h");
assert.equal(reviewLatencyBucket("2026-09-30T20:00:00Z", now), "under_1d");
assert.equal(reviewLatencyBucket("2026-09-27T12:00:00Z", now), "under_7d");
assert.equal(reviewLatencyBucket("2026-08-01T12:00:00Z", now), "over_7d");
assert.equal(reviewLatencyBucket("not a date", now), undefined);
assert.equal(reviewLatencyBucket("2026-10-02T12:00:00Z", now), undefined, "a future date is unknown, not zero");

// --- Users and Owner are separate audiences.
for (const name of ownerEvents) assert.ok(name.startsWith("jarvis_") && !userEvents.has(name), name);
{
  const owner = runSdk({ key: "public-key", legal: true, role: "owner", plan: "owner" });
  owner.context.run.captureProductEvent("screen_viewed", { screen: "overview" });
  owner.context.run.captureProductEvent("useful_action", { action_type: "goal_created" });
  owner.context.run.captureProductEvent("jarvis_section_viewed", { jarvis_section: "chats", plan: "vip", audience: "user" });
  const sent = owner.calls.filter(([name]) => name === "capture").map(([, e]) => e);
  assert.deepEqual(sent.map((e) => e.event), ["jarvis_opened", "jarvis_section_viewed"], "the Owner sends only JARVIS events");
  for (const e of sent) assert.equal(e.properties.audience, "owner");
  assert.equal(sent[1].properties.jarvis_section, "chats");
  assert.equal(sent[0].properties.plan, undefined, "the Owner has no commercial plan");
  assert.deepEqual(runSdk({ key: "public-key", legal: true, role: "admin" }).calls, [], "admins are never tracked");
  assert.deepEqual(runSdk({ key: "public-key", legal: false, role: "owner" }).calls, [], "the Owner needs the legal acceptance too");
}

// --- Enumerations match the screens that exist.
const registry = fs.readFileSync(new URL("../src/products/finva/features/registry.jsx", import.meta.url), "utf8");
const registryBody = registry.slice(registry.indexOf("  return {"), registry.lastIndexOf("};"));
const registryPages = new Set([...registryBody.matchAll(/^ {4}"?([a-z-]+)"?:/gm)].map((m) => m[1]));
assert.deepEqual([...registryPages].sort(), [...userScreens].sort(), "screen enum = every Users page id");
const personal = fs.readFileSync(new URL("../src/personal/PersonalApp.jsx", import.meta.url), "utf8");
const ownerPages = [...personal.matchAll(/case "([^"]+)":/g)].map((m) => m[1]);
assert.ok(ownerPages.length >= 20, "the Owner page switch was found");
for (const page of ownerPages) assert.ok(jarvisSections.has(page), `JARVIS page '${page}' missing from jarvisSections`);
assert.ok(jarvisSections.has("dashboard"));
assert.ok(mailOAuthErrorCodes.has("other"));
for (const [path, module] of [["/user-product/vip/gmail/sync", "mail"], ["/user-product/vip/mail/oauth/complete?flow=secret", "mail"], ["/auth/me", "auth"],
  ["/user-product/vip/strategy-dashboard", "strategy"], ["/user-product/debts/12", "debts"], ["/user-product/movements", "transactions"], ["/weird/place", "other"]]) {
  assert.equal(endpointModule(path), module, path);
}
for (const name of ["login_completed", "logout", "mailbox_connection_failed", "api_error", "app_error"]) assert.ok(analyticsEvents.has(name), name);

// --- Static guard: every event the app emits is in the contract (no silently dropped
// or undeclared events), and no call site passes a sensitive property name.
const sources = [];
const walk = (dir) => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = `${dir}/${entry.name}`;
    if (entry.isDirectory()) walk(full);
    else if (/\.(jsx?|mjs)$/.test(entry.name)) sources.push([full, fs.readFileSync(full, "utf8")]);
  }
};
walk(new URL("../src", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
for (const [file, text] of sources) {
  for (const match of text.matchAll(/(?:trackEvent|captureProductEvent)\(\s*"([a-z_]+)"\s*(?:,\s*\{([^}]*)\})?/g)) {
    assert.ok(analyticsEvents.has(match[1]), `${file}: event '${match[1]}' is not in analyticsContract.js`);
    for (const key of (match[2] || "").matchAll(/([A-Za-z_$][\w$]*)\s*:/g)) {
      assert.doesNotMatch(key[1], SENSITIVE, `${file}: '${match[1]}' passes sensitive property '${key[1]}'`);
    }
  }
}

// --- Login and logout: reported once, only for eligible accounts, logout before the reset.
{
  const ineligible = runSdk({ key: "public-key", legal: false });
  ineligible.context.run.noteLoginCompleted();
  assert.equal(ineligible.calls.filter(([name]) => name === "capture").length, 0, "no event before legal acceptance");
  const login = runSdk({ key: "public-key", legal: true });
  login.context.run.noteLoginCompleted();
  const user = { id: "account-id", role: "user", legal: { required: false }, subscription: { plan: "vip" } };
  login.context.run.setProductAnalyticsUser(user);
  login.context.run.setProductAnalyticsUser(user);  // re-renders never repeat it
  const names = login.calls.filter(([name]) => name === "capture").map(([, e]) => e.event);
  assert.deepEqual(names, ["app_opened", "login_completed"], "one app_opened and one login_completed, no duplicates");
}
const app = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
assert.match(app, /event === "SIGNED_IN" && activeUserId === null && nextUserId\) noteLoginCompleted\(\)/, "only a real sign-in counts as login");
assert.ok(app.indexOf('captureProductEvent("logout")') < app.indexOf("if (identityChanged) setCurrentUser(null)"), "logout is sent before the identity reset");
const telemetry = fs.readFileSync(new URL("../src/lib/telemetry.js", import.meta.url), "utf8");
assert.match(telemetry, /captureProductEvent\("app_error", \{ error_category: "window_error" \}\)/, "app errors carry only a category");
assert.match(telemetry, /captureProductEvent\("app_error", \{ error_category: "render_error" \}\)/, "React render failures are reported as a category only");
const incidents = fs.readFileSync(new URL("../src/lib/incidentReporter.js", import.meta.url), "utf8");
assert.match(incidents, /endpoint: endpointModule\(incident\.path\)/, "API errors carry a module, never the path");

// --- Disabled analytics: nothing is initialized or captured.
{
  const disabled = runSdk({ key: "" });
  disabled.context.run.captureProductEvent("api_error", { endpoint: "mail" });
  assert.deepEqual(disabled.calls, []);
}

console.log("DINCR PostHog explicit-event and sensitive-data contract passed.");
