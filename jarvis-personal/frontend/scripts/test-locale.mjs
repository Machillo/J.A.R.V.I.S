import assert from "node:assert/strict";

const original = globalThis.navigator;
Object.defineProperty(globalThis, "navigator", { configurable: true, value: { languages: ["es-CR", "en-US"], language: "es-CR" } });
const { applyDocumentLanguage, deviceLanguage, localeTag, tx } = await import("../src/lib/locale.js");

assert.equal(deviceLanguage(), "es");
assert.equal(localeTag(), "es-CR");
assert.equal(tx("Guardar", "Save"), "Guardar");

Object.defineProperty(globalThis, "navigator", { configurable: true, value: { languages: ["en-US", "es-CR"], language: "en-US" } });
assert.equal(deviceLanguage(), "en", "the primary phone language must win");
assert.equal(localeTag(), "en-US");
assert.equal(tx("Guardar", "Save"), "Save");

Object.defineProperty(globalThis, "navigator", { configurable: true, value: { languages: undefined, language: "es-MX" } });
assert.equal(deviceLanguage(), "es");

if (original === undefined) delete globalThis.navigator;
else Object.defineProperty(globalThis, "navigator", { configurable: true, value: original });

console.log("Locale detection tests passed.");
