import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const entry = read("../src/main.jsx");
const publicPage = read("../src/pages/PublicInfoPage.jsx");
const accountActions = read("../src/products/finva/components/AccountActions.jsx");
const registry = read("../src/products/finva/features/registry.jsx");
const android = read("../android/variables.gradle");

assert.match(entry, /"\/delete-account"/, "Public deletion page must load without authentication");
assert.match(publicPage, /Perfil o Más → Ajustes de cuenta y plan → Eliminar cuenta/, "Deletion page must describe the in-app deletion path");
assert.match(publicPage, /mailto:soporte@dincr\.com/, "Deletion page must provide public support contact");
assert.match(publicPage, /href="\/privacy"/, "Deletion page must link to the retention policy");
assert.match(accountActions, /await deleteMyAccount\(\)/, "In-app deletion must remain actionable");
for (const plan of ["vip", "basic", "free"]) {
  assert.match(registry, new RegExp(`plan === "${plan}"`), `${plan} navigation must remain present`);
}
assert.match(android, /targetSdkVersion\s*=\s*36/, "Android target SDK requires rechecking before store submission");
// A deletion interrupted after the data was erased can always be finished from the app.
const app = read("../src/App.jsx");
const apiErrors = read("../src/lib/apiErrors.js");
assert.match(apiErrors, /code === "account_deletion_pending" && detail\) message = detail/);
assert.match(app, /setDeletionPending\(error\?\.code === "account_deletion_pending"\)/);
assert.match(app, /deletionPending && <button[\s\S]*?await deleteMyAccount\(\);[\s\S]*?signOut/);
console.log("Store readiness source contracts passed. Live store and device verification remain manual.");
