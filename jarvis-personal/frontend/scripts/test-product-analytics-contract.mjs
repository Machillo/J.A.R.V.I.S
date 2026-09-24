import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { analyticsEvents, analyticsPropertyNames, endpointModule, mailOAuthErrorCodes, safeAnalyticsProperties } from "../src/lib/analyticsContract.js";
import { DINCR_APP_ID, isDincrAppId } from "../src/lib/appIdentity.js";

const sdk = fs.readFileSync(new URL("../src/lib/productAnalytics.js", import.meta.url), "utf8");
const gmail = fs.readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");

assert.deepEqual(safeAnalyticsProperties({
  plan: "vip", platform: "android", success: true, scan_scope: "year_to_date",
  bank: "Banco de mi papá", account: "1234", amount: 5000,
  balance: 7000, debt: 8000, email: "private@example.com", subject: "pago",
  sender: "bank@example.com", description: "salary", token: "private", pdf: "%PDF",
  $current_url: "https://example.com/#access_token=secret", $set: { email: "private@example.com" },
}), { plan: "vip", platform: "android", success: true, scan_scope: "year_to_date" });
assert.deepEqual(safeAnalyticsProperties({ plan: "VIP@gmail.com", platform: "web", source_type: "BAC", screen: "/debts/1234" }), {});
assert.deepEqual(safeAnalyticsProperties({ app_version: "1.9.11", duration_ms: 1288, initial_scan_complete: false }), {
  app_version: "1.9.11", duration_ms: 1000, initial_scan_complete: false,
});
assert.ok(analyticsEvents.has("account_deletion_started"));
assert.equal(analyticsEvents.has("$pageview"), false);
assert.match(sdk, /autocapture: false/);
assert.match(sdk, /capture_pageview: false/);
assert.match(sdk, /disable_session_recording: true/);
assert.match(sdk, /capture_exceptions: false/);
assert.match(sdk, /person_profiles: "never"/);
assert.match(sdk, /before_send:/);
assert.match(sdk, /user\?\.legal\?\.required === false/);
assert.doesNotMatch(sdk, /posthog\.identify\(/);
assert.doesNotMatch(gmail, /bank: item\.|institution_country: item\.|auto_saved: result\./);
assert.match(gmail, /if \(outcome\.provider !== "gmail"\) trackEvent\("mail_connected"/, "Gmail connections are counted once, by the backend");

function runSdk({ key = "", mobile = true, legal = false, appId = "com.dincr.app" } = {}) {
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
    posthog: sdkStub, analyticsEvents, safeAnalyticsProperties, DINCR_APP_ID, isDincrAppId,
    Capacitor: { isNativePlatform: () => mobile, getPlatform: () => "android" },
    env: { VITE_POSTHOG_KEY: key, VITE_POSTHOG_HOST: "https://us.i.posthog.com", VITE_NATIVE_APP_ID: appId },
    window: {},
  };
  vm.runInNewContext(`${source}\nglobalThis.run = { setProductAnalyticsUser, captureProductEvent, noteLoginCompleted };`, context);
  context.posthogConfig = () => sdkStub.config;
  context.run.setProductAnalyticsUser({ id: "account-id", role: "user", legal: { required: !legal }, subscription: { plan: "vip" } });
  return { calls, context };
}

assert.deepEqual(runSdk().calls, [], "missing key is a no-op");
assert.deepEqual(runSdk({ key: "public-key" }).calls, [], "missing legal acceptance is a no-op");
assert.deepEqual(runSdk({ key: "public-key", legal: true, mobile: false }).calls, [], "Vercel preview is excluded");
assert.ok(runSdk({ key: "public-key", legal: true, appId: "com.dincr.app" }).calls.length, "the DINCR iOS build (com.dincr.app) keeps product analytics");
assert.deepEqual(runSdk({ key: "public-key", legal: true, appId: "com.jarvis.personal" }).calls, [], "a non-DINCR build never sends analytics");
const { calls, context } = runSdk({ key: "public-key", legal: true });
assert.deepEqual(calls.filter(([name]) => name === "capture").map(([, event]) => event.event), ["app_opened"]);
context.run.captureProductEvent("transaction_confirmed", { amount: 1234, bank: "BAC", source_type: "email" });
const event = calls.at(-1)[1];
assert.deepEqual(Object.keys(event).sort(), ["event", "properties", "uuid"]);
assert.equal(event.properties.amount, undefined);
assert.equal(event.properties.$current_url, undefined);
assert.equal(event.properties.$set, undefined);
assert.equal(event.properties.email, undefined);
assert.equal(event.properties.source_type, "email");
assert.equal(event.properties.token, "phc_public_project_key", "the public project key is required for ingestion");
assert.equal(event.properties.$process_person_profile, false, "no person profiles");
assert.equal(event.properties.$geoip_disable, true, "no IP geolocation");
assert.deepEqual(Object.keys(event.properties).sort(), ["$geoip_disable", "$process_person_profile", "distinct_id", "environment", "plan", "platform", "source_type", "token"]);
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
context.run.captureProductEvent("unapproved_event", { source_type: "email" });
assert.equal(calls.filter(([name]) => name === "capture").length, 2);
context.run.setProductAnalyticsUser({ id: "second-account", role: "user", legal: { required: false }, subscription: { plan: "free" } });
assert.ok(calls.some(([name]) => name === "reset"), "switching accounts must rotate the anonymous ID");
assert.equal(calls.filter(([name, value]) => name === "capture" && value.event === "app_opened").length, 2);

// --- Privacy guard: no allowed property name may describe financial content,
// mail content, identity or credentials. Adding one to the contract fails here.
const SENSITIVE = /amount|balance|salary|income|debt|iban|account_?(id|number)|workspace|card|sinpe|subject|body|snippet|sender|recipient|counterpart|payee|payer|email|mail_?address|name|token|secret|password|cookie|auth|header|raw|payload|description|merchant|url|path|query|stack|(^|_)message($|_)|(^|_)ip($|_)|phone|user_?id|person/i;
for (const name of analyticsPropertyNames) assert.doesNotMatch(name, SENSITIVE, `analytics property '${name}' looks sensitive`);
const hostile = {
  amount: 12500, balance: 1, salary: 1, debt: 1, iban: "CR05015202001026284066", account_number: "1234",
  card: "4111111111111111", sinpe: "88888888", subject: "Pago", body: "Hola", snippet: "Compra", sender: "banco@x.com",
  counterparty: "Persona", email: "a@b.com", name: "Persona", access_token: "t", refresh_token: "t",
  authorization: "Bearer x", cookie: "c", password: "p", raw_payload: { amount: 1 }, description: "x",
  account_id: "uuid", workspace_id: "uuid", user_id: 1, $current_url: "https://x", $set: { email: "a@b.com" },
  endpoint: "/user-product/vip/gmail/42", status_code: "500", messages_scanned: -1, candidates_pending: 1.5, provider: "yahoo",
};
assert.deepEqual(safeAnalyticsProperties(hostile), {}, "hostile or malformed values never pass");

// --- New categories and bounded counts.
assert.deepEqual(safeAnalyticsProperties({ provider: "microsoft", error_code: "denied", messages_scanned: 250000, candidates_pending: 3, duplicates: 0, status_code: 503, endpoint: "mail", method: "POST", error_category: "server", environment: "production" }),
  { provider: "microsoft", error_code: "denied", messages_scanned: 100000, candidates_pending: 3, duplicates: 0, status_code: 503, endpoint: "mail", method: "POST", error_category: "server", environment: "production" });
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
// Owner-only screens still call trackEvent for a few events; the contract drops them (the
// Owner is never tracked) and no other system receives them.
const OWNER_FIREBASE_ONLY = new Set(["salvavidas_saved", "salvavidas_target_selected"]);
for (const [file, text] of sources) {
  for (const match of text.matchAll(/(?:trackEvent|captureProductEvent)\(\s*"([a-z_]+)"\s*(?:,\s*\{([^}]*)\})?/g)) {
    assert.ok(analyticsEvents.has(match[1]) || OWNER_FIREBASE_ONLY.has(match[1]), `${file}: event '${match[1]}' is not in analyticsContract.js`);
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
