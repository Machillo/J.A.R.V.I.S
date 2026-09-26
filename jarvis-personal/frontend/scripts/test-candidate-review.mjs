import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  createLatestOnly, createReviewGate, reconcileReview, reviewFailure, reviewOutcome, runCandidateReview,
} from "../src/lib/candidateReview.js";

const SUCCESS = /^(Movimiento guardado|Transaction saved|Correo descartado|Email dismissed|Transferencia interna confirmada|Internal transfer confirmed)/;

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
  assert.doesNotMatch(outcome.message, SUCCESS);
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

// After an unknown outcome the refreshed list decides.
const row = (candidate_id, review_status) => ({ candidate_id, review_status });
assert.equal(reconcileReview("accept", 7, [row(7, "confirmed")]).applied, true, "the refresh proves the Accept");
assert.equal(reconcileReview("reject", 7, [row(7, "rejected")]).applied, true, "the refresh proves the Reject");
for (const [action, stored] of [["accept", "rejected"], ["reject", "confirmed"]]) {
  const settled = reconcileReview(action, 7, [row(7, stored)]);
  assert.equal(settled.applied, false);
  assert.equal(settled.status, stored, "the stored status settles the card");
  assert.doesNotMatch(settled.message, SUCCESS);
}
const stillPending = reconcileReview("accept", 7, [row(7, "pending")]);
assert.equal(stillPending.applied, false);
assert.equal(stillPending.status, undefined, "a pending row stays open for a retry");
assert.match(stillPending.message, /intentarlo de nuevo|try again/);
assert.equal(reconcileReview("accept", 7, null).status, undefined, "a failed refresh settles nothing");
assert.match(reconcileReview("accept", 7, null).message, /intentá de nuevo|try again/);
assert.doesNotMatch(reconcileReview("accept", 7, [row(8, "pending")]).message, SUCCESS, "gone from the list is not a success");

// Only the latest refresh may write the list.
const loads = createLatestOnly();
const older = loads.start();
const newer = loads.start();
assert.equal(older(), false, "an older refresh that resolves late is discarded");
assert.equal(newer(), true);

// ---- The Accept/Reject flow, driven with fakes ----
const deferred = () => {
  let resolve; let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
};
const failWith = (status, message = "failed") => async () => { throw Object.assign(new Error(message), { status }); };

function harness({ item = { candidate_id: 7 }, list = [row(7, "pending")] } = {}) {
  const calls = [];
  const state = { mounted: true, busy: "", pageError: "", message: "", notice: null, editorOpen: true, applied: 0, reloads: 0, requests: 0 };
  const flowGate = createReviewGate();
  const reload = async () => { state.reloads += 1; return typeof list === "function" ? list() : list; };
  const run = (action, send) => runCandidateReview({
    gate: flowGate, item, action,
    send: () => { state.requests += 1; return send(); },
    reload, isMounted: () => state.mounted, onApplied: () => { state.applied += 1; },
    ui: {
      begin: () => { calls.push("begin"); state.busy = `${action}-${item.candidate_id}`; state.pageError = ""; state.message = ""; state.notice = null; },
      settle: (outcome) => {
        calls.push("settle"); state.editorOpen = false;
        if (outcome.applied) state.message = outcome.message; else state.pageError = outcome.message;
      },
      pageError: (text) => { calls.push("pageError"); state.message = ""; state.pageError = text; },
      cardError: (text) => { calls.push("cardError"); state.notice = text; },
      end: () => { calls.push("end"); state.busy = ""; },
    },
  });
  return { state, calls, run, gate: flowGate };
}

// Same-tick taps: Accept+Accept, Accept+Reject, Reject+Accept and a burst: one request only.
for (const actions of [["accept", "accept"], ["accept", "reject"], ["reject", "accept"], Array(8).fill("accept")]) {
  const { state, run, gate: flowGate } = harness();
  const pending = deferred();
  const runs = actions.map((action) => run(action, () => pending.promise));
  assert.equal(state.requests, 1, `${actions.join("+")}: only one request leaves while the gate is busy`);
  pending.resolve({ status: actions[0] === "accept" ? "confirmed" : "rejected" });
  assert.deepEqual(await Promise.all(runs), ["applied", ...Array(actions.length - 1).fill("dropped")]);
  assert.equal(flowGate.active, null, "the gate is free afterwards");
  assert.equal(state.applied, 1);
}

// The gate is released on every ending, the controls come back and a retry is possible.
const endings = [
  ["success", async () => ({ status: "confirmed" }), "applied"],
  ["stale", async () => ({ status: "rejected" }), "stale"],
  ["timeout", async () => { throw new Error("La solicitud tardó demasiado. Volvé a intentarlo."); }, "unknown"],
  ["network", failWith(0), "unknown"],
  ["5xx", failWith(503), "unknown"],
  ["404", failWith(404), "unknown"],
  ["unexpected 200", async () => ({ ok: true }), "unknown"],
  ["thrown non-error", async () => { throw undefined; }, "unknown"],
  ["403", failWith(403), "failed"],
  ["422", failWith(422), "failed"],
];
for (const [name, send, expected] of endings) {
  const { state, run, gate: flowGate } = harness();
  assert.equal(await run("accept", send), expected, name);
  assert.equal(flowGate.active, null, `${name}: the gate is released`);
  assert.equal(state.busy, "", `${name}: the controls are restored`);
  if (expected === "applied") assert.match(state.message, SUCCESS);
  else assert.equal(state.message, "", `${name}: no success is shown`);
  assert.equal(await run("accept", async () => ({ status: "confirmed" })), "applied", `${name}: a later retry is possible`);
}

// Definite failures keep the card and the editor, show the reason on it, and neither reload nor retry.
for (const status of [401, 403, 409, 422]) {
  const { state, run } = harness();
  await run("accept", failWith(status, `reason ${status}`));
  assert.equal(state.notice, `reason ${status}`);
  assert.equal(state.editorOpen, true, "the user's corrections are kept");
  assert.equal(state.reloads, 0, `${status} does not trigger an automatic refresh`);
  assert.equal(state.requests, 1, `${status} is not retried automatically`);
}

// Unknown outcomes never assume success or failure: the refreshed list decides.
for (const [stored, action, applied] of [["confirmed", "accept", true], ["rejected", "reject", true], ["rejected", "accept", false], ["confirmed", "reject", false]]) {
  const { state, run } = harness({ list: [row(7, stored)] });
  await run(action, failWith(0));
  assert.equal(state.reloads, 1);
  assert.equal(state.editorOpen, false, "a stored status settles the card");
  assert.equal(Boolean(state.message), applied, `${action} with ${stored} stored: success only if it matches`);
  if (!applied) assert.match(state.pageError, /ya estaba|was already/);
  assert.equal(state.applied, 0, "an unknown outcome is not counted as a review in analytics");
}
{
  const { state, run } = harness({ list: [row(7, "pending")] });
  assert.equal(await run("accept", failWith(502)), "unknown");
  assert.equal(state.editorOpen, true, "still pending: the card stays open");
  assert.match(state.pageError, /sigue pendiente|still pending/);
  assert.equal(state.message, "");
}
{
  const { state, run } = harness({ list: null });
  assert.equal(await run("reject", failWith(0)), "unknown");
  assert.equal(state.editorOpen, true, "the refresh failed too: nothing is removed locally");
  assert.match(state.pageError, /intentá de nuevo|try again/);
  assert.equal(state.message, "");
}

// Two devices: B still shows pending and taps the opposite action; the backend answers A's status.
for (const [bAction, aStored, text] of [["accept", "rejected", /rechazado|rejected/], ["reject", "confirmed", /guardado|saved/]]) {
  const { state, run } = harness({ list: [row(7, aStored)] });
  assert.equal(await run(bAction, async () => ({ status: aStored, candidate_id: 7 })), "stale");
  assert.equal(state.message, "", "device B never shows success");
  assert.match(state.pageError, text);
  assert.equal(state.applied, 0, "a stale outcome is not tracked as a review");
  assert.equal(state.reloads, 1, "B refreshes to the stored state");
}

// Unmount while the request or the refresh is in flight: no UI update afterwards.
{
  const { state, calls, run, gate: flowGate } = harness();
  const pending = deferred();
  const flow = run("accept", () => pending.promise);
  state.mounted = false;
  pending.resolve({ status: "confirmed" });
  assert.equal(await flow, "unmounted");
  assert.deepEqual(calls, ["begin"], "nothing is written after unmount");
  assert.equal(state.applied, 1, "the stored review is still counted");
  assert.equal(flowGate.active, null);
}
{
  const refresh = deferred();
  const { state, calls, run } = harness({ list: () => refresh.promise });
  const flow = run("accept", failWith(500));
  while (state.reloads === 0) await Promise.resolve();
  state.mounted = false;
  refresh.resolve([row(7, "confirmed")]);
  assert.equal(await flow, "unmounted");
  assert.deepEqual(calls, ["begin", "pageError"], "a late refresh after unmount writes nothing and shows no second banner");
}

// The page wires the flow, the latest-only refresh and the accessible states.
const page = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");
const review = page.slice(page.indexOf("const review = "), page.indexOf("const confirmAccount"));
assert.match(review, /runCandidateReview\(\{\s*gate: reviewGate/);
assert.doesNotMatch(review, /setEmails\(/, "the list changes only through a reload from the backend");
assert.match(review, /if \(outcome\.applied\) \{ setError\(""\); setMessage\(outcome\.message\); \}\s*else \{ setMessage\(""\); setError\(outcome\.message\); \}/,
  "a stale outcome goes to the alert, never to the success banner");
const load = page.slice(page.indexOf("const load = useCallback"), page.indexOf("const review = "));
assert.match(load, /const isLatest = loads\.start\(\);/);
assert.ok(load.indexOf("if (!current()) return items;") < load.indexOf("setEmails(items)"), "a stale refresh never writes the list");
assert.match(page, /aria-busy=\{reviewing\}/);
assert.match(page, /className="success-banner" role="status"/);
assert.match(page, /className="onboarding-error" role="alert"/);
console.log("candidate review tests passed");
