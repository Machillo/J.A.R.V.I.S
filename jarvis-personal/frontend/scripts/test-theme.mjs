// DINCR light/dark theme guards (code-level; the UI still needs the physical pass).
//
// Regression: on Android and iPhone, light mode showed dark surfaces. Three causes:
// 1. Users CSS branched on @media (prefers-color-scheme) (the phone) while the app
//    setting lives in html[data-color-mode-resolved]: the two could disagree.
// 2. The Free/Basic/VIP stylesheets hardcoded the dark Figma palette, and Basic/VIP
//    forced it (color-scheme: dark) in light mode.
// 3. main.jsx imported App (and with it the DINCR Users styles) before the global
//    stylesheets, so legacy and native layers overrode DINCR rules of equal
//    specificity, against the layering the file documents.
import assert from "node:assert/strict";
import fs from "node:fs";

const root = new URL("../", import.meta.url);
const read = (file) => fs.readFileSync(new URL(file, root), "utf8");
const cssFiles = (dir) => fs.readdirSync(new URL(dir, root), { withFileTypes: true }).flatMap((entry) => {
  const rel = `${dir}/${entry.name}`;
  if (entry.isDirectory()) return cssFiles(rel);
  return entry.name.endsWith(".css") ? [rel] : [];
});
const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, "");

// 1. One source of truth: no stylesheet branches on the OS color scheme.
for (const file of cssFiles("src")) {
  assert.doesNotMatch(stripComments(read(file)), /prefers-color-scheme/, `${file}: use html[data-color-mode-resolved], not the OS media query`);
}
const colorMode = read("src/lib/colorMode.js");
assert.match(colorMode, /export const initializeColorMode = \(\) => \{[\s\S]*addEventListener\?\.\("change"/, "Automatic follows OS changes while the app is open");
assert.match(colorMode, /dataset\.colorModeResolved = resolved/);

// 2. Plan stylesheets use palette tokens only, and never force a theme.
const palette = stripComments(read("src/products/finva/styles/palette.css"));
const darkBlock = palette.match(/:root \{([^}]*)\}/)[1];
const lightBlock = palette.match(/html\[data-color-mode-resolved="light"\] \{([^}]*)\}/)[1];
const tokens = [...darkBlock.matchAll(/(--finva-[\w-]+):\s*([^;]+);/g)];
assert.ok(tokens.length >= 15, "palette tokens are defined");
for (const [, token, value] of tokens) {
  assert.match(lightBlock, new RegExp(`${token}:\\s*[^;]+;`), `${token} has a light value`);
  assert.ok(!lightBlock.includes(`${token}: ${value};`) || token === "--finva-on-accent", `${token} differs in light mode`);
}
const paletteHexes = tokens.map(([, , value]) => value.trim().toLowerCase()).filter((value) => /^#[0-9a-f]{6}$/.test(value));
for (const file of ["free.css", "basic-figma.css", "vip-figma.css", "account-actions.css", "light-surfaces.css"]) {
  const css = stripComments(read(`src/products/finva/styles/${file}`)).toLowerCase();
  for (const hex of paletteHexes) assert.ok(!css.includes(hex), `${file}: ${hex} must be a palette token`);
  assert.doesNotMatch(css, /color-scheme:\s*dark/, `${file}: never force the dark scheme`);
}
for (const file of cssFiles("src")) {
  for (const rule of stripComments(read(file)).matchAll(/([^{}]*data-color-mode-resolved="light"[^{}]*)\{([^{}]*)\}/g)) {
    assert.doesNotMatch(rule[2], /color-scheme:\s*dark/, `${file}: a light-mode rule forces the dark scheme`);
  }
}

// Palette first, then the plan layers, then the light fixes for shared components.
const usersApp = read("src/users/UsersApp.jsx");
const order = ["palette.css", "free.css", "basic-figma.css", "vip-figma.css", "account-actions.css", "light-surfaces.css"].map((file) => usersApp.indexOf(`styles/${file}"`));
assert.ok(order.every((index, i) => index > 0 && (i === 0 || index > order[i - 1])), "UsersApp imports the palette before the plan stylesheets");

// 3. Global stylesheets are the bottom layer: main.jsx imports them before App.
const main = read("src/main.jsx");
const firstCss = main.indexOf('import "./styles/01-base.css"');
const lastCss = main.lastIndexOf('/styles/operations.css";');
assert.ok(firstCss > 0 && lastCss > firstCss);
for (const component of ['import App from "./App";', 'import PublicInfoPage from "./pages/PublicInfoPage";']) {
  assert.ok(main.indexOf(component) > lastCss, `${component} must come after the global stylesheets (otherwise they override DINCR)`);
}

console.log(`Theme guards passed (${tokens.length} palette tokens, ${cssFiles("src").length} stylesheets).`);
