// DINCR has one administrative authority: the single verified Owner (master plan P0.2d).
// The web app never routes, brands or exempts a session because its role is "admin".
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const app = read("src/App.jsx");

// Owner routing, branding and the release / legal exemptions belong to the Owner alone.
assert.match(app, /const isPersonal = ownerBridgeMode \|\| currentUser\?\.role === "owner";/, "only the Owner gets the Owner app title");
assert.match(app, /if \(currentUser\.role !== "owner" && releasePolicy\?\.required\)/, "only the Owner skips a required update");
assert.match(app, /if \(currentUser\.role !== "owner" && currentUser\.legal\?\.required\)/, "only the Owner skips the legal consent");
assert.match(app, /if \(currentUser\.role === "owner"\) \{/, "only the Owner enters the Owner app");
assert.match(read("src/pages/ProfileSetup.jsx"), /const isJarvis = user\?\.role === "owner";/, "only the Owner gets Owner branding");

// No source file compares a role with "admin".
const roleAdmin = /role\s*(?:===?|!==?)\s*["']admin["']|["']admin["']\s*(?:===?|!==?)\s*\w*role|\badmin:\s*\[\s*["']Administrador/;
const walk = (dir) => readdirSync(dir).flatMap((name) => {
  const path = join(dir, name);
  return statSync(path).isDirectory() ? walk(path) : /\.(jsx?|mjs)$/.test(name) ? [path] : [];
});
const offenders = walk(new URL("../src", import.meta.url).pathname).filter((path) => roleAdmin.test(readFileSync(path, "utf8")));
assert.deepEqual(offenders, [], `a source file recognises an admin role: ${offenders.join(", ")}`);

console.log("single Owner authority (web): ok");
