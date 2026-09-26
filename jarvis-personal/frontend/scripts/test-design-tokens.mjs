// DINCR 2.0 design-token contrast gate.
//
// DESIGN.md (repository root) is the normative token source for the native apps and the
// landing. A token edit that drops a real foreground/background pair below WCAG 2.2 AA, leaves
// a scheme without a counterpart, makes two chart series indistinguishable, or adds a color
// that no check covers must fail here, before it reaches iOS, Android or the web.
//
// Thresholds by element type (WCAG 2.2 AA):
//   - text, including placeholders and text on filled/tonal components: 4.5:1 (SC 1.4.3);
//   - control boundaries, focus indicators, icons and chart marks: 3:1 (SC 1.4.11);
//   - disabled controls are exempt (SC 1.4.3 "inactive user interface component") and
//     decorative separators are not checked (they identify no control or state).
// Chart series are also checked pairwise with the dataviz method: OKLab ΔE×100 ≥ 15 for
// normal vision and ≥ 8 under protan/deutan simulation (Machado et al. 2009, severity 1.0).
import assert from "node:assert/strict";
import fs from "node:fs";

const designPath = new URL("../../../DESIGN.md", import.meta.url);
// Windows checkouts with core.autocrlf=true have CRLF line endings; parse both.
const source = fs.readFileSync(designPath, "utf8").replace(/\r\n/g, "\n");
const frontmatter = source.match(/^---\n([\s\S]*?)\n---/);
assert.ok(frontmatter, "DESIGN.md must start with YAML frontmatter");

const colorsBlock = frontmatter[1].match(/^colors:\n((?:\s{2}.*\n)+)/m);
assert.ok(colorsBlock, "DESIGN.md frontmatter must define colors");
const colors = {};
for (const line of colorsBlock[1].split("\n")) {
  const entry = line.trim();
  if (!entry || entry.startsWith("#")) continue;
  const m = entry.match(/^([a-z0-9-]+):\s*"(#[0-9A-Fa-f]{6})"\s*$/);
  // No silent skip: a token that does not parse would otherwise escape every check.
  assert.ok(m, `DESIGN.md color entry is not a quoted #RRGGBB token: ${entry}`);
  assert.ok(!(m[1] in colors), `duplicate color token ${m[1]}`);
  colors[m[1]] = m[2];
}

const srgbToLinear = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
const luminance = (hex) => {
  const [r, g, b] = srgbToLinear(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const CVD = {
  protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
};
const oklab = ([r, g, b]) => {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
};
const simulate = (rgb, kind) => (kind ? CVD[kind].map((row) =>
  Math.min(1, Math.max(0, row[0] * rgb[0] + row[1] * rgb[1] + row[2] * rgb[2]))) : rgb);
const deltaE = (a, b, kind) => {
  const [x, y] = [a, b].map((hex) => oklab(simulate(srgbToLinear(hex), kind)));
  return 100 * Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
};

const TEXT = 4.5;
const NON_TEXT = 3;
// Neutral layers: screens, cards, list rows, inputs, sheets, dialogs and navigation bars.
const neutral = ["bg", "surface", "surface-2"];
const statusContainers = ["positive-container", "negative-container", "warning-container", "info-container"];
const charts = Object.keys(colors).filter((k) => k.startsWith("chart-"));
const pairs = [
  // Text hierarchy (primary, secondary, metadata/placeholder), links, unselected and selected
  // navigation labels, status and plan text on every neutral layer.
  ...["text", "text-2", "text-muted", "tint", "positive", "negative", "warning", "info", "vip"]
    .flatMap((fg) => neutral.map((bg) => [fg, bg, TEXT])),
  // Control boundaries (fields, outlined controls), focus indicator and chart marks (1.4.11).
  ...["field-border", "focus-ring", ...charts].flatMap((fg) => neutral.map((bg) => [fg, bg, NON_TEXT])),
  // Filled buttons: primary, pressed and destructive confirm.
  ["on-tint", "tint", TEXT],
  ["on-tint", "tint-pressed", TEXT],
  ["on-tint", "negative", TEXT],
  // Tonal: secondary button, selected chip / segment / Android navigation indicator.
  ["on-tint-container", "tint-container", TEXT],
  ["text-2", "tint-container", TEXT],
  ["tint", "tint-container", NON_TEXT],
  // Banners and status rows: body text, supporting text and the status icon/title.
  ...statusContainers.flatMap((bg) => [["text", bg, TEXT], ["text-2", bg, TEXT], [bg.replace("-container", ""), bg, TEXT]]),
  // VIP plan badge.
  ["vip", "vip-container", TEXT],
  ["text", "vip-container", TEXT],
];
// Tokens with no contrast obligation, with the reason. Everything else must be in a pair.
const exempt = {
  line: "decorative separator; control boundaries use field-border",
  "line-strong": "decorative separator (increased-contrast variant)",
  scrim: "overlay tint behind modals; no content is drawn on it",
};

const failures = [];
let checked = 0;
let weakest = null;
const covered = new Set(Object.keys(exempt));
for (const scheme of ["", "dark-"]) {
  for (const [fg, bg, minimum] of pairs) {
    covered.add(fg).add(bg);
    const a = colors[scheme + fg];
    const b = colors[scheme + bg];
    if (!a || !b) {
      failures.push(`missing color token ${!a ? scheme + fg : scheme + bg} (pair ${fg} on ${bg})`);
      continue;
    }
    const ratio = contrast(a, b);
    checked += 1;
    if (!weakest || ratio / minimum < weakest.margin) {
      weakest = { margin: ratio / minimum, text: `${scheme + fg} on ${scheme + bg} ${ratio.toFixed(2)}:1 (min ${minimum})` };
    }
    if (ratio < minimum) failures.push(`${scheme + fg} (${a}) on ${scheme + bg} (${b}) is ${ratio.toFixed(2)}:1, needs ${minimum}:1`);
  }
  // Chart series must be distinguishable from each other, not only from the background.
  for (let i = 0; i < charts.length; i += 1) {
    for (let j = i + 1; j < charts.length; j += 1) {
      const [a, b] = [colors[scheme + charts[i]], colors[scheme + charts[j]]];
      if (!a || !b) continue; // reported by the counterpart check below
      const normal = deltaE(a, b);
      const cvd = Math.min(deltaE(a, b, "protan"), deltaE(a, b, "deutan"));
      checked += 1;
      if (normal < 15 || cvd < 8) {
        failures.push(`${scheme + charts[i]} vs ${scheme + charts[j]} collide: ΔE ${normal.toFixed(1)} normal (min 15), ${cvd.toFixed(1)} CVD (min 8)`);
      }
    }
  }
}

// Every light token has a dark counterpart and vice versa, so no screen can fall back to a
// single-scheme color.
const light = Object.keys(colors).filter((key) => !key.startsWith("dark-"));
for (const key of light) if (!colors[`dark-${key}`]) failures.push(`missing dark counterpart for ${key}`);
for (const key of Object.keys(colors).filter((k) => k.startsWith("dark-"))) {
  if (!colors[key.slice(5)]) failures.push(`dark token ${key} has no light counterpart`);
}
// A new color token must come with the pairs that protect it (or an explicit exemption).
for (const key of light) if (!covered.has(key)) failures.push(`color token ${key} is not covered by any contrast pair or exemption`);

if (failures.length) {
  console.error(`design tokens: ${failures.length} failure(s)\n  - ${failures.join("\n  - ")}`);
  process.exit(1);
}
console.log(`design tokens: ${checked} checks pass in light and dark (${light.length} tokens paired, `
  + `${charts.length} chart series); weakest: ${weakest.text}`);
