import assert from "node:assert/strict";
import fs from "node:fs";
import { movementPreview } from "../src/users/pages/movementPreview.js";

const screen = fs.readFileSync(new URL("../src/users/pages/Finance.jsx", import.meta.url), "utf8");
const history = fs.readFileSync(new URL("../src/users/pages/Transactions.jsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../src/users/services/jarvisApi.js", import.meta.url), "utf8");
assert.match(screen, /setMovementRows\(await getFreeMovements\(\)\)/);
assert.match(history, /getFreeMovements\(\)/);
assert.match(api, /getFreeMovements = \(\) => request\("\/user-product\/free\/movements"\)/);
assert.doesNotMatch(screen, /movements\.slice\(/, "older confirmed movements must not disappear below a preview limit");
assert.match(screen, /item\.editable \? "button" : "div"/, "automated rows stay read-only");

const rows = [
  { movement_id: "salary:1", origin: "salary", transaction_type: "income", transaction_date: "2026-09-22", description: "Salario", editable: true },
  { movement_id: "expense:2", origin: "expense", transaction_type: "expense", transaction_date: "2026-09-21", description: "Compra", editable: true },
  { movement_id: "transaction:3", origin: "transaction", transaction_type: "expense", transaction_date: "2026-01-01", description: "Gmail confirmado", editable: false },
  { movement_id: "transaction:4", origin: "transaction", transaction_type: "income", transaction_date: "2026-01-02", description: "Estado confirmado", editable: false },
];
assert.deepEqual(movementPreview(rows).map(({ movement_id }) => movement_id), ["salary:1", "expense:2", "transaction:4", "transaction:3"]);
assert.deepEqual(movementPreview(rows, "gmail").map(({ movement_id }) => movement_id), ["transaction:3"]);
assert.deepEqual(movementPreview(rows, "", "income").map(({ movement_id }) => movement_id), ["salary:1", "transaction:4"]);
assert.equal(movementPreview(rows).find(({ movement_id }) => movement_id === "transaction:3").editable, false);
assert.equal(rows[2].kind, undefined, "filtering cannot mutate canonical API rows");

console.log("Unified DINCR movements screen uses the workspace-scoped history dataset.");
