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
assert.match(onboarding, /<FinvaWelcomeStory [^>]*onFinish=\{finishWelcome\}/);
assert.match(storage, /finva:first-run-welcome:/);
// Since f166dcc the story is user-paced (no auto-advance), personalized by profile.
assert.doesNotMatch(story, /setTimeout|setInterval|AUTO_ADVANCE/, "slides never advance on their own");
assert.match(story, /const slides = story\(user\)/);
assert.match(story, /className="finva-welcome-next" type="button" onClick=\{next\}/);
assert.match(story, /aria-live="polite"/);
assert.match(story, /Omitir/);

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
