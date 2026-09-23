import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { analyticsEvents, safeAnalyticsProperties } from "../src/lib/analyticsContract.js";

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

function runSdk({ key = "", mobile = true, legal = false } = {}) {
  const calls = [];
  const sdkStub = {
    init: (_token, config) => { calls.push(["init", config]); sdkStub.config = config; },
    capture: (event, props) => { calls.push(["capture", sdkStub.config.before_send({ event, uuid: "random-uuid", properties: { ...props, distinct_id: "random-device-id", $current_url: "https://x/#token=private", $set: { email: "private@example.com" } } })]); },
    opt_in_capturing: () => calls.push(["opt_in"]),
    opt_out_capturing: () => calls.push(["opt_out"]),
    reset: () => calls.push(["reset"]),
  };
  const source = sdk.replace(/^import .*;\n/gm, "").replaceAll("import.meta.env", "env").replace(/export const /g, "const ");
  const context = {
    posthog: sdkStub, analyticsEvents, safeAnalyticsProperties,
    Capacitor: { isNativePlatform: () => mobile, getPlatform: () => "android" },
    env: { VITE_POSTHOG_KEY: key, VITE_POSTHOG_HOST: "https://us.i.posthog.com", VITE_NATIVE_APP_ID: "com.dincr.app" },
    window: {},
  };
  vm.runInNewContext(`${source}\nglobalThis.run = { setProductAnalyticsUser, captureProductEvent };`, context);
  context.run.setProductAnalyticsUser({ id: "account-id", role: "user", legal: { required: !legal }, subscription: { plan: "vip" } });
  return { calls, context };
}

assert.deepEqual(runSdk().calls, [], "missing key is a no-op");
assert.deepEqual(runSdk({ key: "public-key" }).calls, [], "missing legal acceptance is a no-op");
assert.deepEqual(runSdk({ key: "public-key", legal: true, mobile: false }).calls, [], "Vercel preview is excluded");
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
context.run.captureProductEvent("unapproved_event", { source_type: "email" });
assert.equal(calls.filter(([name]) => name === "capture").length, 2);
context.run.setProductAnalyticsUser({ id: "second-account", role: "user", legal: { required: false }, subscription: { plan: "free" } });
assert.ok(calls.some(([name]) => name === "reset"), "switching accounts must rotate the anonymous ID");
assert.equal(calls.filter(([name, value]) => name === "capture" && value.event === "app_opened").length, 2);

console.log("DINCR PostHog explicit-event and sensitive-data contract passed.");
