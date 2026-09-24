import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createSingleFlight } from "../src/lib/useSingleFlight.js";

// A double tap submits twice before React disables the button: only one write may run.
const pending = [];
const once = createSingleFlight((value) => pending.push(value));
let writes = 0;
let release;
const save = once(async (event) => {
  event.preventDefault();
  writes += 1;
  await new Promise((resolve) => { release = resolve; });
  return "saved";
});
const prevented = [];
const tap = () => save({ preventDefault: () => prevented.push(true) });

const first = tap();
const second = await tap();
assert.equal(second, undefined, "the second tap is dropped");
assert.equal(writes, 1);
assert.equal(prevented.length, 2, "both submits are prevented, so the form never reloads the page");
release();
assert.equal(await first, "saved");
assert.deepEqual(pending, [true, false]);
const third = tap();
assert.equal(writes, 2, "a later, separate save works again");
release();
await third;

const failing = createSingleFlight()(async () => { throw new Error("network"); });
await assert.rejects(failing(), /network/);
await assert.rejects(failing(), /network/, "an error releases the guard");

// Every Users form that creates financial records goes through the guard.
const page = (name) => readFileSync(new URL(`../src/users/pages/${name}.jsx`, import.meta.url), "utf8");
for (const [name, handlers] of Object.entries({
  Finance: ["submitIncome", "submitExpense", "saveEdit"],
  Debts: ["submit", "save"],
  Goals: ["submitGoal", "saveGoal", "submitSavings", "saveSavings"],
  Recurring: ["submit"],
})) {
  const source = page(name);
  for (const handler of handlers) assert.match(source, new RegExp(`const ${handler} = once\\(async`), `${name}.${handler}`);
  assert.doesNotMatch(source, /<button className="finva-button finva-button-primary">/, `${name} submit buttons are disabled while saving`);
}

console.log("DINCR double-submit guard passed.");
