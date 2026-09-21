import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const vip = readFileSync(new URL("../src/products/finva/features/vip/VipScreens.jsx", import.meta.url), "utf8");
const basic = readFileSync(new URL("../src/products/finva/features/basic/BasicScreens.jsx", import.meta.url), "utf8");
const free = readFileSync(new URL("../src/products/finva/features/free/FreeScreens.jsx", import.meta.url), "utf8");
const registry = readFileSync(new URL("../src/products/finva/features/registry.jsx", import.meta.url), "utf8");
const navigation = readFileSync(new URL("../src/products/finva/navigation/FinvaNavigation.jsx", import.meta.url), "utf8");

assert.match(vip, /onNavigate\?\.\("settings"\)/, "VIP must expose account and plan settings");
assert.match(vip, /onNavigate\?\.\("feedback"\)/, "VIP must expose support reporting");
assert.match(basic, /onNavigate\("settings"\)/, "Basic must expose account and plan settings");
assert.match(basic, /onNavigate\("feedback"\)/, "Basic must expose support reporting");
assert.match(free, /onNavigate\("plan-settings"\)/, "Free must expose account and plan settings");
assert.match(free, /onNavigate\("feedback"\)/, "Free must expose support reporting");
assert.match(vip, /Debes sincronizar tu email/, "VIP aguinaldo must explain that email sync is required");
assert.match(vip, /onNavigate\?\.\("gmail"\)/, "VIP aguinaldo must link to Gmail setup");
assert.match(registry, /"vip-aguinaldo": plan === "vip" \? gated\("gmail_automation"/, "Aguinaldo must remain VIP-only and Gmail-gated");
assert.match(navigation, /\["vip-aguinaldo", tx\("Aguinaldo"/, "VIP navigation must expose Aguinaldo");

console.log("FINVA settings/support and VIP aguinaldo navigation contracts passed.");
