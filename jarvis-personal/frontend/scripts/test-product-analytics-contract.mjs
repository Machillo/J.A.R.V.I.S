import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { analyticsEvents, safeAnalyticsProperties } from "../src/lib/analyticsContract.js";
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
  vm.runInNewContext(`${source}\nglobalThis.run = { setProductAnalyticsUser, captureProductEvent };`, context);
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
assert.deepEqual(Object.keys(event.properties).sort(), ["$geoip_disable", "$process_person_profile", "distinct_id", "plan", "platform", "source_type", "token"]);

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

console.log("DINCR PostHog explicit-event and sensitive-data contract passed.");
