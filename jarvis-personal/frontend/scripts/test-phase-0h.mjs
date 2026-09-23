import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(resolve(here, path), "utf8");

const onboarding = read("../src/pages/DincrOnboarding.jsx");
const story = read("../src/pages/DincrWelcomeStory.jsx");
const storage = read("../src/lib/firstRunExperience.js");
const styles = read("../src/pages/DincrOnboarding.css");

assert.match(onboarding, /shouldShowDincrWelcome\(user\?\.id\)/);
assert.match(onboarding, /markDincrWelcomeSeen\(user\?\.id\)/);
assert.match(onboarding, /<DincrWelcomeStory [^>]*onFinish=\{finishWelcome\}/);
assert.match(storage, /dincr:first-run-welcome:/);
assert.match(story, /AUTO_ADVANCE_MS = 3500/);
assert.match(story, /Omitir/);
assert.match(story, /sin pedirte llenar un formulario financiero/);
assert.match(styles, /prefers-reduced-motion: reduce/);

const stored = new Map();
globalThis.window = {
  localStorage: {
    getItem: (key) => stored.get(key) || null,
    setItem: (key, value) => stored.set(key, value),
  },
};
const firstRun = await import("../src/lib/firstRunExperience.js");
assert.equal(firstRun.shouldShowDincrWelcome("account-a"), true);
firstRun.markDincrWelcomeSeen("account-a");
assert.equal(firstRun.shouldShowDincrWelcome("account-a"), false);
assert.equal(firstRun.shouldShowDincrWelcome("account-b"), true);

console.log("Phase 0H first-run welcome contract passed.");
