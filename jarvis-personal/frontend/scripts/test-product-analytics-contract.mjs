import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../src/lib/productAnalytics.js", import.meta.url), "utf8");
const gmail = fs.readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");

for (const forbidden of ["google_email", "subject", "sender", "description", "amount", "account_last4"]) {
  const analyticsCalls = [...gmail.matchAll(/trackEvent\([\s\S]*?\n\s*}\);/g)].map((match) => match[0]).join("\n");
  assert.equal(analyticsCalls.includes(`${forbidden}:`), false, `Forbidden analytics property: ${forbidden}`);
}

assert.match(source, /autocapture: false/);
assert.match(source, /disable_session_recording: true/);
assert.match(source, /opt_out_capturing_by_default: true/);
assert.match(source, /role !== "owner" && role !== "admin"/);
assert.match(source, /legalAccepted/);
assert.match(source, /allowedEvents/);
assert.match(source, /allowedProperties/);

console.log("PostHog privacy contract: OK");
