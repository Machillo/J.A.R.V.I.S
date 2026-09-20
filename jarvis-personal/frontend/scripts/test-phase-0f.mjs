import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const flags = read("../src/lib/featureFlags.js");
const users = read("../src/users/UsersApp.jsx");
const registry = read("../src/products/finva/features/registry.jsx");
const navigation = read("../src/products/finva/navigation/FinvaNavigation.jsx");
const owner = read("../src/pages/ProductOperations.jsx");

for (const key of ["financial_writes", "gmail_automation", "vip_intelligence", "advanced_reports", "store_billing"]) {
  assert.match(flags, new RegExp(key));
}
assert.match(flags, /authenticatedFetch/);
assert.match(flags, /localStorage\.setItem/);
assert.match(flags, /SAFE_FEATURE_DEFAULTS/);
assert.match(users, /setInterval\(refresh, 60_000\)/);
assert.match(users, /financial_writes/);
assert.match(registry, /FeatureUnavailable/);
assert.match(registry, /gated\("gmail_automation"/);
assert.match(navigation, /featureEnabled\(featureFlags, "vip_intelligence"\)/);
assert.match(owner, /Motivo del cambio/);
assert.match(owner, /updateOperationalFeatureFlag/);

console.log("Phase 0F feature flags and kill switches contract passed.");
