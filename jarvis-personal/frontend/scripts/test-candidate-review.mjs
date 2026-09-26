import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createReviewGate, reviewFailure, reviewOutcome } from "../src/lib/candidateReview.js";

// A double tap, or Accept and Reject in the same frame: only the first review runs.
const gate = createReviewGate();
assert.equal(gate.begin(7, "accept"), true);
assert.equal(gate.begin(7, "accept"), false, "a repeated tap is dropped");
assert.equal(gate.begin(7, "reject"), false, "Reject cannot race a running Accept");
assert.equal(gate.begin(8, "accept"), false, "one review at a time for the whole inbox");
assert.deepEqual(gate.active, { candidateId: 7, action: "accept" });
gate.end();
assert.equal(gate.begin(7, "reject"), true, "the lock is released after the request settles");
gate.end();

// Success is reported only when the stored status is the one the action produces.
assert.equal(reviewOutcome("accept", { status: "confirmed", transaction_id: 3 }).applied, true);
assert.equal(reviewOutcome("reject", { status: "rejected" }).applied, true);
for (const [action, stored] of [["accept", "rejected"], ["reject", "confirmed"], ["accept", "duplicate"], ["accept", undefined]]) {
  const outcome = reviewOutcome(action, stored ? { status: stored } : {});
  assert.equal(outcome.applied, false, `${action} over ${stored} is not reported as done`);
  assert.doesNotMatch(outcome.message, /^(Movimiento guardado|Transaction saved|Correo descartado|Email dismissed)/);
}

// Failures keep the candidate; unknown outcomes refresh the list before a retry.
for (const status of [0, 500, 502, 503]) assert.equal(reviewFailure({ status }).ambiguous, true, `status ${status} is ambiguous`);
assert.equal(reviewFailure(new Error("La solicitud tardó demasiado.")).ambiguous, true, "a timeout has no status and is ambiguous");
assert.equal(reviewFailure({ status: 404 }).ambiguous, true, "a vanished candidate refreshes the list");
for (const status of [401, 403, 409, 422]) {
  const failure = reviewFailure({ status, message: `server says ${status}` });
  assert.equal(failure.ambiguous, false);
  assert.equal(failure.message, `server says ${status}`, "the API error message is shown as is");
}

// The inbox uses the gate and the stored status, and never removes a candidate itself.
const page = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");
const review = page.slice(page.indexOf("const review = async"), page.indexOf("const confirmAccount"));
assert.match(review, /if \(!reviewGate\.begin\(item\.candidate_id, action\)\) return;/);
assert.match(review, /reviewOutcome\(action, result/);
assert.match(review, /reviewGate\.end\(\)/);
assert.ok(review.indexOf("setMessage(outcome.message)") > review.indexOf("await acceptVipGmailCandidate"), "feedback only after the backend answers");
assert.doesNotMatch(review, /setEmails\(/, "the list changes only through a reload from the backend");
assert.match(page, /aria-busy=\{reviewing\}/);
console.log("candidate review tests passed");
