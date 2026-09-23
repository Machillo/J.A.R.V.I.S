import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const entry = read("../src/main.jsx");
const publicPage = read("../src/pages/PublicInfoPage.jsx");
const accountActions = read("../src/products/finva/components/AccountActions.jsx");
const registry = read("../src/products/finva/features/registry.jsx");
const android = read("../android/variables.gradle");

assert.match(entry, /"\/delete-account"/, "Public deletion page must load without authentication");
assert.match(publicPage, /href="\/"[^>]*>Ingresar a DINCR para eliminar mi cuenta/, "Deletion page must link to the authenticated deletion path");
assert.match(publicPage, /href="\/privacy"/, "Deletion page must link to the retention policy");
assert.match(accountActions, /await deleteMyAccount\(\)/, "In-app deletion must remain actionable");
for (const plan of ["vip", "basic", "free"]) {
  assert.match(registry, new RegExp(`plan === "${plan}"`), `${plan} navigation must remain present`);
}
assert.match(android, /targetSdkVersion\s*=\s*36/, "Android target SDK requires rechecking before store submission");
console.log("Store readiness source contracts passed. Live store and device verification remain manual.");
