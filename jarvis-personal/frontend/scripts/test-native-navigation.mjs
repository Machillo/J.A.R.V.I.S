import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const hook = readFileSync(new URL("../src/products/dincr/navigation/useDincrNavigation.js", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/users/UsersApp.jsx", import.meta.url), "utf8");
const dialog = readFileSync(new URL("../src/users/components/DincrDialog.jsx", import.meta.url), "utf8");
const sheet = readFileSync(new URL("../src/users/components/DincrFormSheet.jsx", import.meta.url), "utf8");
const feedback = readFileSync(new URL("../src/users/pages/Feedback.jsx", import.meta.url), "utf8");
const settings = readFileSync(new URL("../src/users/pages/Settings.jsx", import.meta.url), "utf8");

assert.match(hook, /history\.pushState/, "DINCR destinations create real history entries");
assert.match(hook, /history\.back\(\)/, "back returns to the previous entry instead of forcing home");
assert.match(hook, /addListener\("backButton"/, "Android system back is integrated");
assert.match(hook, /minimizeApp\(\)/, "Android only leaves DINCR when the stack is empty");
assert.match(hook, /clientX <= EDGE_START_PX/, "iOS edge swipes are recognized");
assert.match(hook, /dincr:native-back/, "nested flows can consume back before page navigation");
assert.match(dialog, /useDincrBackHandler/, "system back closes an open confirmation or amount dialog first");
assert.match(sheet, /useDincrBackHandler\(onClose, open\)/, "system back closes an open form sheet first");
assert.match(feedback, /useDincrBackHandler/, "system back closes the support chat before leaving support");
assert.match(settings, /Boolean\(confirming\)/, "system back closes the plan dialog before leaving settings");
assert.match(app, /useDincrNavigation\(initialPage\)/, "all DINCR plans share the native history stack");
assert.doesNotMatch(app, /navigate:\s*setPage/, "feature navigation cannot bypass the history stack");

console.log("DINCR native back navigation contract passed.");
