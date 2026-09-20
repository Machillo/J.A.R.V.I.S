import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const app = read("../src/App.jsx");
const helper = read("../src/lib/releasePolicy.js");
const notice = read("../src/components/ReleaseUpdateNotice.jsx");
const users = read("../src/users/UsersApp.jsx");
const owner = read("../src/pages/ProductOperations.jsx");

assert.match(helper, /product-ops\/release-policy/);
assert.match(helper, /AbortController/);
assert.match(app, /releasePolicy\?\.required/);
assert.match(app, /catch \{[\s\S]*setReleasePolicy\(null\)/);
assert.match(notice, /Actualización necesaria/);
assert.match(notice, /Browser\.open/);
assert.match(users, /releasePolicy\?\.status === "optional"/);
assert.match(users, /dismissRelease/);
assert.match(owner, /Versión mínima/);
assert.match(owner, /updateReleasePolicy/);

console.log("Phase 0E release policy contract passed.");
