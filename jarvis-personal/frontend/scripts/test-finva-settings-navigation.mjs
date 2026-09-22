import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const vip = readFileSync(new URL("../src/products/finva/features/vip/VipScreens.jsx", import.meta.url), "utf8");
const basic = readFileSync(new URL("../src/products/finva/features/basic/BasicScreens.jsx", import.meta.url), "utf8");
const free = readFileSync(new URL("../src/products/finva/features/free/FreeScreens.jsx", import.meta.url), "utf8");
const registry = readFileSync(new URL("../src/products/finva/features/registry.jsx", import.meta.url), "utf8");
const navigation = readFileSync(new URL("../src/products/finva/navigation/FinvaNavigation.jsx", import.meta.url), "utf8");
const hubs = readFileSync(new URL("../src/products/finva/features/hubs/FinvaHubs.jsx", import.meta.url), "utf8");
const settings = readFileSync(new URL("../src/users/pages/Settings.jsx", import.meta.url), "utf8");
const gmail = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");

assert.match(vip, /onNavigate\?\.\("settings"\)/, "VIP must expose account and plan settings");
assert.match(vip, /onNavigate\?\.\("feedback"\)/, "VIP must expose support reporting");
assert.match(basic, /onNavigate\("settings"\)/, "Basic must expose account and plan settings");
assert.match(basic, /onNavigate\("feedback"\)/, "Basic must expose support reporting");
assert.match(free, /onNavigate\("plan-settings"\)/, "Free must expose account and plan settings");
assert.match(free, /onNavigate\("feedback"\)/, "Free must expose support reporting");
assert.match(vip, /Debes sincronizar tu email/, "VIP aguinaldo must explain that email sync is required");
assert.match(vip, /onNavigate\?\.\("gmail"\)/, "VIP aguinaldo must link to Gmail setup");
assert.match(registry, /"vip-aguinaldo": plan === "vip" \? gated\("gmail_automation"/, "Aguinaldo must remain VIP-only and Gmail-gated");
assert.match(hubs, /item\(navigate, "vip-aguinaldo", tx\("Aguinaldo"/, "VIP Plan hub must expose Aguinaldo");
assert.match(hubs, /if \(plan === "vip"\).*item\(navigate, "gmail"/s, "Financial email review must remain VIP-only");
for (const key of ["overview", "finance", "plan", "advisor", "profile"]) {
  assert.match(navigation, new RegExp(`key: "${key}"`), `Primary navigation must expose ${key}`);
}
assert.doesNotMatch(navigation, /key: "more"/, "Primary navigation must not restore the oversized More destination");
assert.match(settings, /<AccountActions onLogout=\{onLogout\} variant=\{currentPlan\}/, "Basic and VIP settings must expose logout and permanent account deletion");
assert.match(free, /<AccountActions onLogout=\{onLogout\}/, "Free settings must preserve permanent account deletion");
assert.match(registry, /<SettingsPage user=\{user\} onUserChange=\{onUserChange\} onLogout=\{onLogout\}/, "Settings must receive the logout callback used after deletion");
assert.match(gmail, /getVipFinancialIdentity/, "VIP Gmail must load the user's financial identity");
assert.match(gmail, /confirmVipFinancialAccount/, "Detected accounts must require an explicit ownership decision");
assert.match(gmail, /DINCR no incluirá una cuenta detectada en tu patrimonio sin tu confirmación/, "Detected accounts must explain that ownership is not assumed");

console.log("DINCR information architecture, settings and VIP Gmail contracts passed.");
