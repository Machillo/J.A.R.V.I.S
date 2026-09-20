import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const app = read("../src/users/UsersApp.jsx");
const feedback = read("../src/users/pages/Feedback.jsx");
const api = read("../src/users/services/jarvisApi.js");

assert.match(api, /getPlatformHealth/);
assert.match(api, /finva:api-recovered/);
assert.match(app, /finva-health-mode/);
assert.match(app, /Sin conexión/);
assert.match(app, /Modo degradado/);
assert.match(app, /window\.addEventListener\("offline"/);
assert.match(app, /window\.addEventListener\("online"/);
assert.match(feedback, /Estado de FINVA/);
assert.match(feedback, /Operando normalmente/);
assert.match(feedback, /Servicio degradado/);

console.log("Phase 0B health and degraded-mode contract: OK");
