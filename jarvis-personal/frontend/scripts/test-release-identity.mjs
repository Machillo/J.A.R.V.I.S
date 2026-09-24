import assert from "node:assert/strict";
import { identityProblems, readIdentity } from "./release-version.mjs";

// The web bundle shows Android's versionName on every platform, and the release
// policy compares it: both native projects must carry the same identity.
assert.deepEqual(identityProblems(readIdentity()), [], "Android and iOS share version and build number");

const gradle = 'versionCode 36\n        versionName "1.9.11"';
const xcode = "MARKETING_VERSION = 1.9.7;\nCURRENT_PROJECT_VERSION = 32;\nMARKETING_VERSION = 1.9.7;\nCURRENT_PROJECT_VERSION = 32;";
assert.deepEqual(identityProblems(readIdentity(gradle, xcode)), [
  "Versión distinta: Android 1.9.11 vs iOS 1.9.7",
  "Build distinto: Android 36 vs iOS 32",
]);
assert.equal(identityProblems(readIdentity(gradle, "MARKETING_VERSION = 1.9.11;\nMARKETING_VERSION = 1.9.10;\nCURRENT_PROJECT_VERSION = 36;")).length, 1);

console.log("DINCR release identity is consistent across Android and iOS.");
