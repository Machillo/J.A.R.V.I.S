import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const recovery = readFileSync(new URL("../src/lib/operationRecovery.js", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/users/services/jarvisApi.js", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const shell = readFileSync(new URL("../src/users/UsersApp.jsx", import.meta.url), "utf8");

assert.match(recovery, /RECOVERABLE_METHODS = new Set\(\["POST", "PUT", "PATCH"\]\)/);
assert.doesNotMatch(recovery, /RECOVERABLE_METHODS = .*DELETE/);
assert.match(recovery, /X-Idempotency-Key/);
assert.match(recovery, /QUEUE_PREFIX.*userId/);
assert.match(recovery, /MAX_AGE_MS = 24 \* 60 \* 60 \* 1000/);
assert.match(recovery, /MAX_BODY_BYTES = 32 \* 1024/);
assert.match(api, /recoverableFetch/);
assert.match(api, /flushPendingOperations/);
assert.match(app, /appStateChange[\s\S]*flushPendingOperations/);
assert.match(shell, /Cambio protegido/);
assert.match(shell, /Cambio recuperado/);

console.log("Phase 0D operation recovery contract passed.");
