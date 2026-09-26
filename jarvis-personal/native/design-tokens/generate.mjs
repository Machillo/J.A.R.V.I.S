#!/usr/bin/env node
// Generates the native design tokens from /DESIGN.md (the normative DINCR 2.0 source).
//
//   node jarvis-personal/native/design-tokens/generate.mjs          write the generated files
//   node jarvis-personal/native/design-tokens/generate.mjs --check  fail if they are stale
//
// Outputs are committed so the apps build without Node. Never edit them by hand.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const designPath = path.join(repoRoot, "DESIGN.md");
const outputs = {
  swift: path.join(here, "../ios/DincrKit/Sources/DincrDesign/Generated/DincrTokens.swift"),
  kotlin: path.join(here, "../android/core/design/src/main/kotlin/com/dincr/design/generated/DincrTokens.kt"),
};

export function parseTokens(source) {
  const frontmatter = source.match(/^---\n([\s\S]*?)\n---/);
  if (!frontmatter) throw new Error("DESIGN.md must start with YAML frontmatter");
  const block = (name) => {
    const match = frontmatter[1].match(new RegExp(`^${name}:\\n((?:\\s{2}.*\\n)+)`, "m"));
    if (!match) throw new Error(`DESIGN.md frontmatter is missing ${name}`);
    return match[1];
  };
  const pairs = (text) => [...text.matchAll(/^\s{2}"?([a-z0-9-]+)"?:\s*"([^"]+)"/gm)].map((m) => [m[1], m[2]]);
  const colors = Object.fromEntries(pairs(block("colors")));
  const light = Object.keys(colors).filter((key) => !key.startsWith("dark-"));
  for (const key of light) {
    if (!colors[`dark-${key}`]) throw new Error(`missing dark counterpart for ${key}`);
  }
  const px = (value) => {
    const number = Number(String(value).replace("px", ""));
    if (!Number.isFinite(number)) throw new Error(`not a px value: ${value}`);
    return number;
  };
  const scale = (name) => pairs(block(name)).map(([key, value]) => [key, px(value)]);
  const version = frontmatter[1].match(/^version:\s*(\S+)/m)?.[1] || "0.0.0";
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

export function render(source) {
  const tokens = parseTokens(source);
  return { swift: swift(tokens), kotlin: kotlin(tokens) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const rendered = render(fs.readFileSync(designPath, "utf8"));
  const check = process.argv.includes("--check");
  let stale = 0;
  for (const [kind, file] of Object.entries(outputs)) {
    const current = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
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
