import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(resolve(here, path), "utf8");

const onboarding = read("../src/pages/FinvaOnboarding.jsx");
const story = read("../src/pages/FinvaWelcomeStory.jsx");
const storage = read("../src/lib/firstRunExperience.js");
const styles = read("../src/pages/FinvaOnboarding.css");

assert.match(onboarding, /shouldShowFinvaWelcome\(user\?\.id\)/);
assert.match(onboarding, /markFinvaWelcomeSeen\(user\?\.id\)/);
assert.match(onboarding, /<FinvaWelcomeStory onFinish=\{finishWelcome\}/);
assert.match(storage, /finva:first-run-welcome:/);
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
assert.equal(firstRun.shouldShowFinvaWelcome("account-a"), true);
firstRun.markFinvaWelcomeSeen("account-a");
assert.equal(firstRun.shouldShowFinvaWelcome("account-a"), false);
assert.equal(firstRun.shouldShowFinvaWelcome("account-b"), true);

console.log("Phase 0H first-run welcome contract passed.");
