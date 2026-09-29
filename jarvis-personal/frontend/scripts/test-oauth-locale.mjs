import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { getOAuthLocale, normalizeOAuthLocale } from "../src/lib/oauthLocale.js";

// Normalization: DINCR ships English and Spanish; everything else is English.
for (const [value, expected] of [
  ["en", "en"], ["en-US", "en"], ["en-GB", "en"], ["EN_us", "en"],
  ["es", "es"], ["es-CR", "es"], ["es-ES", "es"], ["es-419", "es"],
  ["fr-FR", "en"], ["pt-BR", "en"], ["", null], [undefined, null], [null, null],
]) assert.equal(normalizeOAuthLocale(value), expected, `normalize ${value}`);

const none = { languages: [], language: undefined };
// App language.
assert.equal(getOAuthLocale({ ...none, appLanguage: "en" }), "en", "app EN → EN");
assert.equal(getOAuthLocale({ ...none, appLanguage: "es" }), "es", "app ES → ES");
// Device languages.
assert.equal(getOAuthLocale({ languages: ["en-US"] }), "en");
assert.equal(getOAuthLocale({ languages: ["en-GB", "es-CR"] }), "en");
assert.equal(getOAuthLocale({ languages: ["es-CR", "en-US"] }), "es");
assert.equal(getOAuthLocale({ languages: ["es-419"] }), "es");
assert.equal(getOAuthLocale({ languages: [], language: "es-CR" }), "es", "navigator.language when languages is empty");
assert.equal(getOAuthLocale({ languages: ["fr-FR", "es-CR"] }), "en", "unknown first language → English, like the app copy");
assert.equal(getOAuthLocale(none), "en", "nothing known → English");
// An explicit preference wins over the device, in both directions.
assert.equal(getOAuthLocale({ preference: "en", appLanguage: "es", languages: ["es-CR"] }), "en");
assert.equal(getOAuthLocale({ preference: "es", appLanguage: "en", languages: ["en-US"] }), "es");
// The app language wins over the device list.
assert.equal(getOAuthLocale({ appLanguage: "en", languages: ["es-CR"] }), "en");

// Only Gmail's connect call carries the locale; Outlook and every other OAuth value are untouched.
const api = readFileSync(new URL("../src/users/services/jarvisApi.js", import.meta.url), "utf8");
assert.match(api, /connectVipGmail = \(importScope, locale\) => json\("\/user-product\/vip\/gmail\/connect", "POST", \{ import_scope: importScope, locale \}\)/);
assert.match(api, /connectVipMicrosoftMail = \(importScope\) => json\("\/user-product\/vip\/mail\/microsoft\/connect", "POST", \{ import_scope: importScope \}\)/);
const page = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");
assert.match(page, /connectVipGmail\(scope, getOAuthLocale\(\{ appLanguage: deviceLanguage\(\) \}\)\)/);
assert.match(page, /Browser\.open\(\{ url: response\.authorization_url, presentationStyle: "popover" \}\)/);

console.log("OAuth locale: app/device language → en|es for Google's consent screens; English fallback.");
