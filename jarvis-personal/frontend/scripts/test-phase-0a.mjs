import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const feedback = read("../src/users/pages/Feedback.jsx");
const fetcher = read("../src/lib/authenticatedFetch.js");
const reporter = read("../src/lib/incidentReporter.js");
const apiErrors = read("../src/lib/apiErrors.js");
const vite = read("../vite.config.js");

assert.match(feedback, /support-bubble--/);
assert.match(feedback, /Tengo un problema/);
assert.match(feedback, /¿Qué hiciste y qué ocurrió después\?/);
assert.match(feedback, /support-chat-overlay/);
assert.match(feedback, /Sí, se resolvió/);
assert.match(feedback, /No, sigue igual/);
assert.match(feedback, /updateFeedbackResolution/);
assert.doesNotMatch(feedback, /1\.8\.5/);
assert.match(vite, /versionName/);

assert.match(fetcher, /SAFE_METHODS = new Set\(\["GET", "HEAD", "OPTIONS"\]\)/);
assert.match(fetcher, /"X-Request-ID": requestId/);
assert.match(fetcher, /"X-Retry-Attempt": String\(retryCount\)/);
assert.match(reporter, /\/product-ops\/incidents/);
assert.match(reporter, /DEDUPE_MS = 15 \* 60 \* 1000/);
assert.match(reporter, /split\(\/\[\?#\]\//);
assert.match(reporter, /replace\(\/\\\/\\d\+/);
assert.doesNotMatch(reporter, /salary|debt|transaction|account_number|card_number/i);
assert.match(apiErrors, /captureIncident\(incident\)/);

console.log("Phase 0A frontend contract: OK");
