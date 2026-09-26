// DINCR 2.0 design-token contrast gate.
//
// DESIGN.md (repository root) is the normative token source for the native apps and the
// landing. A token edit that drops a text or control pair below WCAG 2.2 AA must fail here,
// before it reaches iOS, Android or the web. Pairs are checked in the light scheme and again
// with the `dark-` prefixed tokens.
import assert from "node:assert/strict";
import fs from "node:fs";

const designPath = new URL("../../../DESIGN.md", import.meta.url);
const source = fs.readFileSync(designPath, "utf8");
const frontmatter = source.match(/^---\n([\s\S]*?)\n---/);
assert.ok(frontmatter, "DESIGN.md must start with YAML frontmatter");

const colorsBlock = frontmatter[1].match(/^colors:\n((?:\s{2}.*\n)+)/m);
assert.ok(colorsBlock, "DESIGN.md frontmatter must define colors");
const colors = Object.fromEntries(
  [...colorsBlock[1].matchAll(/^\s{2}([a-z0-9-]+):\s*"(#[0-9A-Fa-f]{6})"/gm)].map((m) => [m[1], m[2]]),
);

const luminance = (hex) => {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
};
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const TEXT = 4.5;
const NON_TEXT = 3;
const surfaces = ["bg", "surface", "surface-2"];
const pairs = [
  // Text on every neutral layer.
  ...["text", "text-2", "text-muted", "tint", "positive", "negative", "warning", "info", "vip"]
    .flatMap((fg) => surfaces.map((bg) => [fg, bg, TEXT])),
  // Control boundaries, focus and chart marks (WCAG 1.4.11).
  ...["field-border", "focus-ring", "chart-income", "chart-expense"]
    .flatMap((fg) => surfaces.map((bg) => [fg, bg, NON_TEXT])),
  // Filled and tonal components.
  ["on-tint", "tint", TEXT],
  ["on-tint", "tint-pressed", TEXT],
  ["on-tint", "negative", TEXT],
  ["on-tint-container", "tint-container", TEXT],
  ["text", "positive-container", TEXT],
  ["positive", "positive-container", TEXT],
  ["text", "negative-container", TEXT],
  ["negative", "negative-container", TEXT],
  ["text", "warning-container", TEXT],
  ["warning", "warning-container", TEXT],
  ["text", "info-container", TEXT],
  ["info", "info-container", TEXT],
  ["vip", "vip-container", TEXT],
];

let checked = 0;
for (const scheme of ["", "dark-"]) {
  for (const [fg, bg, minimum] of pairs) {
    const a = colors[scheme + fg];
    const b = colors[scheme + bg];
    assert.ok(a, `DESIGN.md is missing color token ${scheme + fg}`);
    assert.ok(b, `DESIGN.md is missing color token ${scheme + bg}`);
    const ratio = contrast(a, b);
    assert.ok(
      ratio >= minimum,
      `${scheme + fg} (${a}) on ${scheme + bg} (${b}) is ${ratio.toFixed(2)}:1, needs ${minimum}:1`,
    );
    checked += 1;
  }
}

// Every light token has a dark counterpart and vice versa, so no screen can fall back to a
// single-scheme color.
const light = Object.keys(colors).filter((key) => !key.startsWith("dark-"));
for (const key of light) assert.ok(colors[`dark-${key}`], `missing dark counterpart for ${key}`);
for (const key of Object.keys(colors).filter((k) => k.startsWith("dark-"))) {
  assert.ok(colors[key.slice(5)], `dark token ${key} has no light counterpart`);
}

console.log(`design tokens: ${checked} contrast pairs pass in light and dark; ${light.length} tokens paired`);
