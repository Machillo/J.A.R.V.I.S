// DINCR v1.0 visual freeze: structural guards for breakages found in the
// pre-launch visual pass. These are code-level checks, not pixel tests; the
// UI still needs the physical Android/iOS pass.
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

// Bottom navigation: one label size for every plan, shrinking on narrow phones
// so "Movimientos"/"Transactions" fit five tabs at 320-360px.
assert.match(read("src/products/finva/styles/product.css"), /--finva-nav-label-size:\s*clamp\(/);
for (const file of ["free.css", "basic-figma.css", "vip-figma.css"]) {
  const css = read(`src/products/finva/styles/${file}`);
  assert.match(css, /\.native-nav-label\{font-size:var\(--finva-nav-label-size\)/, `${file} uses the shared nav label size`);
}

// Movimientos filter bar: no fixed height under its 40px tap targets (a 34px bar
// clipped the tabs and scrolled them vertically on phones).
for (const file of ["free.css", "basic-figma.css"]) {
  const bar = read(`src/products/finva/styles/${file}`).match(/\.free-filter-tabs\{([^}]*)\}/)[1];
  assert.doesNotMatch(bar, /(^|;)height:/, `${file}: the filter bar sizes to its tabs`);
}

// History: the three-column table becomes stacked rows on phones instead of
// hiding the amount and actions off screen.
const usersCss = read("src/users/users.css");
assert.match(usersCss, /@media \(max-width: 560px\) \{\s*\.users-app \.movement-head \{ display:none; \}/);
assert.match(usersCss, /\.users-app \.movement-row \{ min-width:0;/);

// VIP strategy reuses the Owner disclosure component; its styles must apply to DINCR too.
assert.match(read("src/products/jarvis/styles/disclosure.css"), /:is\(\.native-product--jarvis, \.native-product--finva\) \.jarvis-disclosure \{/);
assert.match(read("src/products/finva/styles/vip-figma.css"), /\.native-product--finva \.jarvis-disclosure\{--jarvis-line:/);

// Long VIP titles and row labels wrap instead of being cut with an ellipsis.
const vipCss = read("src/products/finva/styles/vip-figma.css");
assert.match(vipCss, /\.vip-screen-header h1\{white-space:normal;/);
assert.match(vipCss, /\.vip-data-row span\{white-space:normal;/);

// Effects must not return a promise (React calls the return value as cleanup).
for (const file of ["src/users/pages/Budget.jsx", "src/products/finva/features/vip/VipScreens.jsx"]) {
  const source = read(file);
  for (const match of source.matchAll(/useEffect\(([A-Za-z_$][\w$]*)\s*,/g)) {
    const definition = source.match(new RegExp(`const ${match[1]}\\s*=\\s*(async\\s*)?\\([^)]*\\)\\s*=>\\s*(\\{)?`));
    assert.ok(definition && !definition[1] && definition[2], `${file}: useEffect(${match[1]}) must not return a promise`);
  }
}

// API codes are labelled, never rendered raw.
assert.match(read("src/users/pages/Debts.jsx"), /codeLabel\("debtTypes", debt\.debt_type\)/);
assert.match(read("src/users/pages/Recurring.jsx"), /codeLabel\("frequencies", item\.frequency\)/);
assert.doesNotMatch(read("src/users/pages/Debts.jsx"), /advanced \? "DINCR · BASIC" : "DINCR · FREE"/, "VIP debts must not be labelled BASIC");

// Debt payments are outflows in the history, not income.
const history = read("src/users/pages/Transactions.jsx");
assert.match(history, /row\.transaction_type === "income" \? "\+" : "−"/);

// Error states render instead of crashing.
assert.match(read("src/users/pages/FinancialSituation.jsx"), /if \(!data\) return <div className="panel error" role="alert">\{error\}<\/div>;/);

// Public settings must not show internal wording.
assert.doesNotMatch(read("src/users/pages/Settings.jsx"), /tx\("Desarrollo", "Development"\)/);
assert.match(read("src/users/components/AppLockSettings.jsx"), /role="switch" aria-checked=\{config\.enabled\} aria-label=/);

// Every public CRC formatter shows ₡ in English too.
for (const file of ["src/users/pages/Debts.jsx", "src/products/finva/features/vip/VipScreens.jsx", "src/users/pages/Budget.jsx"]) {
  assert.match(read(file), /currency: ?"CRC", ?currencyDisplay: ?"narrowSymbol"/, `${file} uses the ₡ symbol`);
}
// Finance formats in the account's base currency through the shared formatter,
// which also uses the narrow symbol (₡, not "CRC", in English).
assert.match(read("src/users/pages/Finance.jsx"), /const money = \(value\) => formatMoney\(value\);/);
assert.match(read("src/lib/currency.js"), /currencyDisplay: "narrowSymbol"/);
assert.equal(new Intl.NumberFormat("en-US", { style: "currency", currency: "CRC", currencyDisplay: "narrowSymbol", maximumFractionDigits: 0 }).format(1500), "₡1,500");

// Owner operations styles are loaded (they used to live in the never-imported App.css).
assert.ok(!fs.existsSync(new URL("../src/App.css", import.meta.url)), "the unused Vite template App.css stays removed");
assert.match(read("src/main.jsx"), /import "\.\/products\/jarvis\/styles\/operations\.css";/);
assert.match(read("src/products/jarvis/styles/operations.css"), /\.product-ops-page\{/);

// Owner stays out of DINCR Users.
const registry = read("src/products/finva/features/registry.jsx");
assert.doesNotMatch(registry, /personal\/PersonalApp|products\/jarvis\/(?!components\/JarvisDisclosure)/, "the Users registry does not import Owner screens");

// Owner Finance on phones: grid tracks are bounded so a long category name or a
// large CRC/USD amount cannot widen the column past the viewport (Gastos), and the
// monthly trend chart scrolls inside its own box with an intrinsic height, so the
// legend, cards and note after it are normal vertical flow (Análisis).
const financeModules = read("src/styles/08-finance-modules.css");
assert.match(financeModules, /\.spending-donut-workspace\{display:grid;grid-template-columns:minmax\(0,1fr\)/);
assert.match(financeModules, /\.spending-donut-main\{display:grid;grid-template-columns:repeat\(auto-fit,minmax\(min\(100%,290px\),1fr\)\)/);
assert.match(financeModules, /\.spending-donut-legend\{display:grid;grid-template-columns:minmax\(0,1fr\)/);
assert.match(financeModules, /@media \(max-width:900px\)\{\.spending-donut-main\{grid-template-columns:minmax\(0,1fr\)\}\.spending-donut-legend span strong\{white-space:normal;overflow-wrap:anywhere\}/);
assert.match(financeModules, /\.trend-summary-grid-four\{grid-template-columns:repeat\(auto-fit,minmax\(min\(100%,190px\),1fr\)\)\}/);
assert.match(financeModules, /\.finance-trend-plot\{min-width:0;overflow-x:auto;overflow-y:hidden;/);
assert.match(financeModules, /\.finance-trend-plot svg\{display:block;width:100%;height:auto;aspect-ratio:820\/330;overflow:hidden\}/);
assert.doesNotMatch(financeModules, /\.finance-trend-chart\{overflow-x:auto\}|\.finance-trend-chart svg\{/, "only the plot box scrolls");
const financeCycle = read("src/styles/06-finance-cycle.css");
assert.match(financeCycle, /\.finance-detail-list,\s*\.full-debt-list \{\s*display: grid;[^}]*grid-template-columns: minmax\(0, 1fr\);/);
assert.match(financeCycle, /\.finance-detail-row div \{\s*min-width: 0;[^}]*max-width: 100%;/);
const ownerFinance = read("src/pages/Finance.jsx");
const trendChart = ownerFinance.slice(ownerFinance.indexOf("function MonthlyFinanceTrendChart"), ownerFinance.indexOf("export function ReceivablesPanel"));
const plotStart = trendChart.indexOf('<div className="finance-trend-plot">');
const plotEnd = trendChart.indexOf("</svg>", plotStart);
assert.ok(plotStart > 0 && plotEnd > plotStart, "the trend SVG lives in its own plot box");
assert.ok(trendChart.indexOf('className="trend-summary-grid') > plotEnd, "summary cards follow the plot box");
assert.match(trendChart, /<svg viewBox=\{`0 0 \$\{width\} \$\{height\}`\} width=\{width\} height=\{height\}/, "the SVG has an intrinsic size");

console.log("DINCR v1.0 visual freeze guards passed.");
