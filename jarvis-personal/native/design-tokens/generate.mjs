#!/usr/bin/env node
// Generates the native design tokens from /DESIGN.md (the normative DINCR 2.0 source) and the
// personal-appearance alternatives from appearance.json (appearance.mjs).
//
//   node jarvis-personal/native/design-tokens/generate.mjs          write the generated files
//   node jarvis-personal/native/design-tokens/generate.mjs --check  fail if they are stale
//
// Outputs are committed so the apps build without Node. Never edit them by hand.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { contrastFailures, kotlinCatalog, kotlinTokens, parseAppearance, swiftCatalog, swiftTokens } from "./appearance.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const designPath = path.join(repoRoot, "DESIGN.md");
const appearancePath = path.join(here, "appearance.json");
const outputs = {
  swift: path.join(here, "../ios/DincrKit/Sources/DincrDesign/Generated/DincrTokens.swift"),
  kotlin: path.join(here, "../android/core/design/src/main/kotlin/com/dincr/design/generated/DincrTokens.kt"),
  swiftAppearance: path.join(here, "../ios/DincrKit/Sources/DincrDesign/Generated/DincrAppearanceTokens.swift"),
  swiftCatalog: path.join(here, "../ios/DincrKit/Sources/DincrCore/Generated/AppearanceCatalog.swift"),
  kotlinAppearance: path.join(here, "../android/core/design/src/main/kotlin/com/dincr/design/generated/DincrAppearanceTokens.kt"),
  kotlinCatalog: path.join(here, "../android/core/data/src/main/kotlin/com/dincr/data/generated/AppearanceCatalog.kt"),
};

// Windows checkouts with core.autocrlf turn LF into CRLF; the tokens do not depend on it.
const lf = (text) => text.replace(/\r\n/g, "\n");

export function parseTokens(raw) {
  const source = lf(raw);
  const frontmatter = source.match(/^---\n([\s\S]*?)\n---/);
  if (!frontmatter) throw new Error("DESIGN.md must start with YAML frontmatter");
  const block = (name) => {
    const match = frontmatter[1].match(new RegExp(`^${name}:\\n((?:\\s{2}.*\\n)+)`, "m"));
    if (!match) throw new Error(`DESIGN.md frontmatter is missing ${name}`);
    return match[1];
  };
  // Strict: every entry of a block must parse. A line that does not would otherwise be skipped
  // silently and its token would vanish from both apps without any error.
  const pairs = (name) => {
    const entries = [];
    for (const line of block(name).split("\n")) {
      if (!line.trim() || line.trim().startsWith("#")) continue;
      const m = line.match(/^\s{2}"?([a-z0-9-]+)"?:\s*"([^"]+)"\s*$/);
      if (!m) throw new Error(`DESIGN.md ${name}: entry does not parse: ${line.trim()}`);
      if (entries.some(([key]) => key === m[1])) throw new Error(`DESIGN.md ${name}: duplicate token ${m[1]}`);
      entries.push([m[1], m[2]]);
    }
    if (!entries.length) throw new Error(`DESIGN.md ${name} is empty`);
    return entries;
  };
  const colors = Object.fromEntries(pairs("colors"));
  for (const [key, value] of Object.entries(colors)) {
    if (!/^#[0-9A-Fa-f]{6}$/.test(value)) throw new Error(`DESIGN.md color ${key} is not #RRGGBB: ${value}`);
  }
  const light = Object.keys(colors).filter((key) => !key.startsWith("dark-"));
  for (const key of light) {
    if (!colors[`dark-${key}`]) throw new Error(`missing dark counterpart for ${key}`);
  }
  for (const key of Object.keys(colors).filter((key) => key.startsWith("dark-"))) {
    if (!colors[key.slice(5)]) throw new Error(`dark token ${key} has no light counterpart`);
  }
  const px = (value) => {
    if (!/^\d+(\.\d+)?px$/.test(String(value))) throw new Error(`not a px value: ${value}`);
    return Number(String(value).slice(0, -2));
  };
  const scale = (name) => pairs(name).map(([key, value]) => [key, px(value)]);
  // The version is written into Swift and Kotlin string literals: semver only.
  const version = frontmatter[1].match(/^version:\s*(\S+)\s*$/m)?.[1];
  if (!version || !/^\d+\.\d+\.\d+$/.test(version)) throw new Error(`DESIGN.md version must be MAJOR.MINOR.PATCH, got ${version}`);
  return {
    version,
    colors: light.map((key) => ({ key, light: colors[key], dark: colors[`dark-${key}`] })),
    spacing: scale("spacing"),
    radius: scale("rounded"),
    icon: scale("icon"),
  };
}

const camel = (key) => key.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase());
const swiftName = (key) => (/^\d/.test(key) ? `s${key}` : camel(key));
const hex = (value) => value.replace("#", "").toUpperCase();

function swift(tokens) {
  const colorLines = tokens.colors
    .map(({ key, light, dark }) => `    static let ${camel(key)} = Color(light: 0x${hex(light)}, dark: 0x${hex(dark)})`)
    .join("\n");
  const scaleLines = (entries) => entries.map(([key, value]) => `    static let ${swiftName(key)}: CGFloat = ${value}`).join("\n");
  return `// GENERATED from /DESIGN.md (DINCR ${tokens.version}) by jarvis-personal/native/design-tokens/generate.mjs.
// Do not edit. Change DESIGN.md and run the generator.
import SwiftUI

public enum DincrColor {
${colorLines.replace(/ {4}static/g, "    public static")}
}

public enum DincrSpacing {
${scaleLines(tokens.spacing).replace(/ {4}static/g, "    public static")}
}

public enum DincrRadius {
${scaleLines(tokens.radius).replace(/ {4}static/g, "    public static")}
}

public enum DincrIconSize {
${scaleLines(tokens.icon).replace(/ {4}static/g, "    public static")}
}

public enum DincrTokensVersion {
    public static let value = "${tokens.version}"
}
`;
}

function kotlin(tokens) {
  const colorLines = tokens.colors
    .map(({ key, light, dark }) => `    val ${camel(key)} = DincrColorPair(light = Color(0xFF${hex(light)}), dark = Color(0xFF${hex(dark)}))`)
    .join("\n");
  const scaleLines = (entries) => entries.map(([key, value]) => `    val ${swiftName(key)} = ${value}.dp`).join("\n");
  return `// GENERATED from /DESIGN.md (DINCR ${tokens.version}) by jarvis-personal/native/design-tokens/generate.mjs.
// Do not edit. Change DESIGN.md and run the generator.
package com.dincr.design.generated

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

data class DincrColorPair(val light: Color, val dark: Color)

object DincrColors {
${colorLines}
}

object DincrSpacing {
${scaleLines(tokens.spacing)}
}

object DincrRadius {
${scaleLines(tokens.radius)}
}

object DincrIconSize {
${scaleLines(tokens.icon)}
}

const val DINCR_TOKENS_VERSION = "${tokens.version}"
`;
}

/** DESIGN.md's colors as one map: light keys and their `dark-` counterparts. */
export function colorMap(tokens) {
  return Object.fromEntries(tokens.colors.flatMap(({ key, light, dark }) => [[key, light], [`dark-${key}`, dark]]));
}

/**
 * The appearance alternatives, validated against DESIGN.md: the classic palette and accent are
 * exactly DESIGN.md's (so an account on the classic set sees today's app), and every combination
 * keeps the contrast rules.
 */
export function checkedAppearance(tokens, rawAppearance) {
  const appearance = parseAppearance(rawAppearance);
  const base = colorMap(tokens);
  const classicPalette = appearance.palettes[appearance.options.palette.classic];
  const classicAccent = appearance.accents[appearance.options.accent.classic];
  for (const mode of ["light", "dark"]) {
    const prefix = mode === "dark" ? "dark-" : "";
    for (const [set, name] of [[classicPalette[mode], "palette"], [classicAccent[mode], "accent"]]) {
      for (const [key, value] of Object.entries(set)) {
        if (base[prefix + key] !== value) throw new Error(`appearance.json classic ${name} ${mode}.${key} is ${value}, DESIGN.md says ${base[prefix + key]}`);
      }
    }
  }
  const failures = contrastFailures(appearance, base);
  if (failures.length) throw new Error(`appearance.json contrast:\n  ${failures.join("\n  ")}`);
  return appearance;
}

export function render(source, rawAppearance = fs.readFileSync(appearancePath, "utf8")) {
  const tokens = parseTokens(source);
  const appearance = checkedAppearance(tokens, rawAppearance);
  return {
    swift: swift(tokens),
    kotlin: kotlin(tokens),
    swiftAppearance: swiftTokens(appearance, tokens.version),
    swiftCatalog: swiftCatalog(appearance, tokens.version),
    kotlinAppearance: kotlinTokens(appearance, tokens.version),
    kotlinCatalog: kotlinCatalog(appearance, tokens.version),
  };
}

const kinds = { DincrColor: "colors", DincrColors: "colors", DincrSpacing: "spacing", DincrRadius: "radius", DincrIconSize: "icon" };

/** Qualified token references (`DincrColor.tint`, `DincrSpacing.s4`…) the apps use but DESIGN.md no longer defines. */
export function missingReferences(tokens, sources) {
  const defined = {
    colors: new Set(tokens.colors.map(({ key }) => camel(key))),
    spacing: new Set(tokens.spacing.map(([key]) => swiftName(key))),
    radius: new Set(tokens.radius.map(([key]) => swiftName(key))),
    icon: new Set(tokens.icon.map(([key]) => swiftName(key))),
  };
  const missing = new Set();
  for (const text of sources) {
    for (const [, type, name] of text.matchAll(/\b(DincrColors?|DincrSpacing|DincrRadius|DincrIconSize)\.([A-Za-z0-9]+)\b/g)) {
      if (!defined[kinds[type]].has(name)) missing.add(`${type}.${name}`);
    }
  }
  return [...missing].sort();
}

/** The Swift and Kotlin sources of both apps, without build output or the generated files. */
export function appSources() {
  const files = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (["build", ".gradle", ".build", "Generated", "generated", "DerivedData"].includes(entry.name)) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (/\.(swift|kt)$/.test(entry.name)) files.push(fs.readFileSync(full, "utf8"));
    }
  };
  [path.join(here, "../ios"), path.join(here, "../android")].filter((root) => fs.existsSync(root)).forEach(walk);
  return files;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const source = fs.readFileSync(designPath, "utf8");
  const rendered = render(source);
  const check = process.argv.includes("--check");
  // A token the apps use must still exist; otherwise the build fails later, far from the cause.
  const missing = missingReferences(parseTokens(source), appSources());
  if (missing.length) {
    console.error(`DESIGN.md no longer defines tokens the apps use: ${missing.join(", ")}`);
    process.exit(1);
  }
  let stale = 0;
  for (const [kind, file] of Object.entries(outputs)) {
    const current = fs.existsSync(file) ? lf(fs.readFileSync(file, "utf8")) : null;
    if (current === rendered[kind]) continue;
    if (check) {
      console.error(`stale: ${path.relative(repoRoot, file)} — run node jarvis-personal/native/design-tokens/generate.mjs`);
      stale += 1;
    } else {
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, rendered[kind]);
      console.log(`wrote ${path.relative(repoRoot, file)}`);
    }
  }
  if (stale) process.exit(1);
  if (check) console.log("native design tokens are current");
}
