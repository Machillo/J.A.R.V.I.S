// The color styles of color-styles.json: validated with the appearance contrast rules and turned
// into Swift and Kotlin. Companion of appearance.mjs; see generate.mjs.
import { contrast, contrastFailures } from "./appearance.mjs";

const NEUTRALS = ["bg", "surface", "surface-2", "line", "line-strong", "field-border", "text", "text-2", "text-muted"];
const ACCENT = ["tint", "tint-pressed", "tint-container", "on-tint", "on-tint-container", "focus-ring"];
const hex = (value) => `0x${value.slice(1).toUpperCase()}`;
const pick = (source, keys) => Object.fromEntries(keys.map((key) => [key, source[key]]));

export function parseColorStyles(raw) {
  const data = JSON.parse(raw);
  if (!data.styles?.[data.default]) throw new Error("color-styles.json: unknown default");
  for (const [id, style] of Object.entries(data.styles)) {
    if (!style.es || !style.en) throw new Error(`color-styles.json ${id}: missing name`);
    if (!style.swatches?.length) throw new Error(`color-styles.json ${id}: missing swatches`);
    if (id === data.default) continue;
    for (const mode of ["light", "dark"]) {
      for (const key of [...NEUTRALS, ...ACCENT]) {
        if (!/^#[0-9A-Fa-f]{6}$/.test(style[mode]?.[key] ?? "")) throw new Error(`color-styles.json ${id}.${mode}.${key} is not #RRGGBB`);
      }
    }
  }
  return data;
}

/** Each style against the same rules as an appearance, plus white text on its hero. */
export function colorStyleFailures(data, base) {
  const failures = [];
  for (const [id, style] of Object.entries(data.styles)) {
    if (id === data.default) continue;
    const pair = (keys) => ({ light: pick(style.light, keys), dark: pick(style.dark, keys) });
    failures.push(...contrastFailures({ palettes: { [id]: pair(NEUTRALS) }, accents: { [id]: pair(ACCENT) } }, base));
    for (const [label, fg, bg] of [["white/hero", "#FFFFFF", style.hero], ["on-hero-2/hero", style["on-hero-2"], style.hero], ["white/hero-control", "#FFFFFF", style["hero-control"]]]) {
      const ratio = contrast(fg, bg);
      if (ratio < 4.5) failures.push(`${id} ${label}: ${ratio.toFixed(2)}:1 (< 4.5)`);
    }
  }
  return failures;
}

const swiftColors = (style) => {
  if (!style.light) return "nil";
  const c = (key) => `Color(light: ${hex(style.light[key])}, dark: ${hex(style.dark[key])})`;
  const same = (key) => `Color(light: ${hex(style[key])}, dark: ${hex(style[key])})`;
  return `DincrColorStyle.Colors(
            bg: ${c("bg")}, surface: ${c("surface")}, surface2: ${c("surface-2")}, border: ${c("line")}, fieldBorder: ${c("field-border")},
            text: ${c("text")}, text2: ${c("text-2")}, textMuted: ${c("text-muted")},
            accent: ${c("tint")}, accentActive: ${c("tint-pressed")}, onAccent: ${c("on-tint")},
            accentContainer: ${c("tint-container")}, onAccentContainer: ${c("on-tint-container")},
            hero: ${same("hero")}, heroControl: ${same("hero-control")}, onHero2: ${same("on-hero-2")})`;
};

export function swiftColorStyles(data) {
  const items = Object.entries(data.styles).map(([id, s]) => `    DincrColorStyle(id: "${id}", nameEs: "${s.es}", nameEn: "${s.en}", swatches: [${s.swatches.map(hex).join(", ")}], colors: ${swiftColors(s)}),`);
  return `// GENERATED from design-tokens/color-styles.json by generate.mjs. Do not edit.
import SwiftUI

public enum DincrColorStyles {
    public static let defaultID = "${data.default}"
    public static let all: [DincrColorStyle] = [
${items.join("\n")}
    ]
}
`;
}

const kotlinColors = (style) => {
  if (!style.light) return "null";
  const c = (key) => `DincrColorPair(Color(0xFF${style.light[key].slice(1).toUpperCase()}), Color(0xFF${style.dark[key].slice(1).toUpperCase()}))`;
  const same = (key) => `Color(0xFF${style[key].slice(1).toUpperCase()})`;
  return `DincrStyleColors(
            bg = ${c("bg")}, surface = ${c("surface")}, surface2 = ${c("surface-2")}, line = ${c("line")}, lineStrong = ${c("line-strong")}, fieldBorder = ${c("field-border")},
            text = ${c("text")}, text2 = ${c("text-2")}, textMuted = ${c("text-muted")},
            tint = ${c("tint")}, tintPressed = ${c("tint-pressed")}, tintContainer = ${c("tint-container")}, onTint = ${c("on-tint")}, onTintContainer = ${c("on-tint-container")},
            hero = ${same("hero")}, heroControl = ${same("hero-control")}, onHero2 = ${same("on-hero-2")},
        )`;
};

export function kotlinColorStyles(data) {
  const items = Object.entries(data.styles).map(([id, s]) => `        DincrColorStyle("${id}", "${s.es}", "${s.en}", listOf(${s.swatches.map((v) => `Color(0xFF${v.slice(1).toUpperCase()})`).join(", ")}), ${kotlinColors(s)}),`);
  return `// GENERATED from design-tokens/color-styles.json by generate.mjs. Do not edit.
package com.dincr.design.generated

import androidx.compose.ui.graphics.Color
import com.dincr.design.DincrColorStyle
import com.dincr.design.DincrStyleColors

object DincrColorStyles {
    const val DEFAULT_ID = "${data.default}"
    val all: List<DincrColorStyle> = listOf(
${items.join("\n")}
    )
}
`;
}
