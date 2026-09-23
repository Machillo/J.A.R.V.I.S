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
assert.match(registry, /"vip-aguinaldo": plan === "vip" \? advisory\(gated\("gmail_automation", .*\), "aguinaldo"\)/, "Aguinaldo must remain VIP-only, Gmail-gated and show its estimate disclaimer");
assert.match(registry, /strategy: advisory\(/, "Strategy must show the not-financial-advice disclaimer");
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

// Movements confirmed from Gmail or statements live in the full history, not in the
// manual income/expense list, so every plan must reach it from "Movimientos".
const finance = readFileSync(new URL("../src/users/pages/Finance.jsx", import.meta.url), "utf8");
const history = readFileSync(new URL("../src/users/pages/Transactions.jsx", import.meta.url), "utf8");
assert.match(registry, /finance: <Finance plan=\{plan\} onNavigate=\{navigate\} \/>/, "Movimientos must receive navigation for every plan");
assert.match(finance, /onNavigate\("transactions"\)/, "Movimientos must link to the full history");
assert.match(registry, /transactions: <Transactions plan=\{plan\} \/>/, "The full history must know the current plan");
assert.doesNotMatch(history, /DINCR · FREE/, "The full history must not label Basic or VIP users as Free");
assert.match(free, /onNavigate\("transactions"\)/, "Free must keep its existing full-history entry");
assert.match(gmail, /setError\(outlookErrorMessage\(result\)\)/, "Outlook callback errors must be shown as readable messages");
assert.doesNotMatch(gmail, /No se pudo conectar Outlook \(\$\{result\}\)/, "Raw Outlook error codes must not be shown to users");

console.log("DINCR information architecture, settings and VIP Gmail contracts passed.");
