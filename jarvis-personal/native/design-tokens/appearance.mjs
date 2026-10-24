// Personal appearance tokens (appearance.json): parsing, validation and the Swift/Kotlin outputs.
// Used by generate.mjs; tested by generate.test.mjs. The base tokens stay in /DESIGN.md.
const HEX = /^#[0-9A-Fa-f]{6}$/;
const NEUTRALS = ["bg", "surface", "surface-2", "line", "line-strong", "field-border", "text", "text-2", "text-muted"];
const NEUTRAL_EXTRAS = ["positive", "glow"];
const ACCENT = ["tint", "tint-pressed", "tint-container", "on-tint", "on-tint-container", "focus-ring"];
const OPTION_KEYS = ["theme", "palette", "accent", "text_size", "typeface", "density", "surfaces"];
const ID = /^[a-z][a-z0-9_]*$/;

const fail = (message) => {
  throw new Error(`appearance.json: ${message}`);
};

const px = (value, where) => {
  if (!/^\d+(\.\d+)?px$/.test(String(value))) fail(`${where} is not a px value: ${value}`);
  return Number(String(value).slice(0, -2));
};

function checkColorSet(set, keys, extras, where) {
  for (const key of keys) if (!HEX.test(set?.[key] ?? "")) fail(`${where}.${key} must be #RRGGBB`);
  for (const key of Object.keys(set)) {
    if (!keys.includes(key) && !extras.includes(key)) fail(`${where} has an unknown token ${key}`);
    if (!HEX.test(set[key])) fail(`${where}.${key} must be #RRGGBB`);
  }
}

/** Strict parse: every option, palette and accent is complete; nothing is silently dropped. */
export function parseAppearance(raw) {
  const json = typeof raw === "string" ? JSON.parse(raw) : raw;
  if (json.version !== 1) fail(`version must be 1, got ${json.version}`);
  const options = {};
  for (const key of OPTION_KEYS) {
    const option = json.options?.[key];
    if (!option) fail(`missing option ${key}`);
    const values = Object.entries(option.values ?? {});
    if (!values.length) fail(`option ${key} has no values`);
    for (const [id, label] of values) {
      if (!ID.test(id)) fail(`option ${key} value id ${id} is not [a-z0-9_]`);
      if (!label.es || !label.en) fail(`option ${key}.${id} needs es and en labels`);
      if (key === "text_size" && !(label.scale >= 0.8 && label.scale <= 1.5)) fail(`text_size.${id} scale must be within 0.8–1.5`);
    }
    const ids = values.map(([id]) => id);
    for (const which of ["default", "classic"]) {
      if (!ids.includes(option[which])) fail(`option ${key}.${which} is not one of its values`);
    }
    options[key] = { default: option.default, classic: option.classic, values: values.map(([id, label]) => ({ id, ...label })) };
  }
  const palettes = Object.entries(json.palettes ?? {});
  const accents = Object.entries(json.accents ?? {});
  const ids = (key) => options[key].values.map((value) => value.id).sort().join(",");
  if (palettes.map(([id]) => id).sort().join(",") !== ids("palette")) fail("palettes must match options.palette exactly");
  if (accents.map(([id]) => id).sort().join(",") !== ids("accent")) fail("accents must match options.accent exactly");
  for (const [id, pair] of palettes) {
    for (const mode of ["light", "dark"]) checkColorSet(pair[mode], NEUTRALS, NEUTRAL_EXTRAS, `palettes.${id}.${mode}`);
    // An optional token overrides DESIGN.md in both schemes or in neither (no half-defined pair).
    for (const key of NEUTRAL_EXTRAS) if (!pair.light[key] !== !pair.dark[key]) fail(`palettes.${id}.${key} must be set in light and dark, or in neither`);
  }
  for (const [id, pair] of accents) for (const mode of ["light", "dark"]) checkColorSet(pair[mode], ACCENT, [], `accents.${id}.${mode}`);
  const shapes = {};
  for (const { id } of options.surfaces.values) {
    const shape = json.shapes?.[id];
    if (!shape) fail(`missing shapes.${id}`);
    shapes[id] = { card: px(shape.card, `shapes.${id}.card`), control: px(shape.control, `shapes.${id}.control`) };
  }
  const density = {};
  for (const { id } of options.density.values) {
    const value = json.density?.[id];
    if (!value) fail(`missing density.${id}`);
    density[id] = { gap: px(value.gap, `density.${id}.gap`), cardPadding: px(value["card-padding"], `density.${id}.card-padding`), rowMin: px(value["row-min"], `density.${id}.row-min`) };
    if (density[id].rowMin < 48) fail(`density.${id}.row-min must keep 48px touch targets`);
  }
  return { version: json.version, options, palettes: Object.fromEntries(palettes), accents: Object.fromEntries(accents), shapes, density };
}

// WCAG 2.x relative luminance and contrast ratio.
const channel = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const luminance = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * channel(((n >> 16) & 255) / 255) + 0.7152 * channel(((n >> 8) & 255) / 255) + 0.0722 * channel((n & 255) / 255);
};
export const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

/**
 * Every palette × accent × scheme keeps DESIGN.md's contrast rules: text ≥ 4.5:1 on every neutral
 * layer, control boundaries and focus ≥ 3:1, labels on filled and tonal accents ≥ 4.5:1, status
 * colors used as text ≥ 4.5:1, chart series ≥ 3:1. [base] is DESIGN.md's color map (light keys and
 * `dark-` keys). Returns the failures as readable strings (empty when everything passes).
 */
export function contrastFailures(appearance, base) {
  const failures = [];
  const need = (label, fg, bg, min) => {
    const ratio = contrast(fg, bg);
    if (ratio < min) failures.push(`${label}: ${fg} on ${bg} is ${ratio.toFixed(2)}:1 (< ${min})`);
  };
  for (const [paletteId, pair] of Object.entries(appearance.palettes)) {
    for (const mode of ["light", "dark"]) {
      const n = pair[mode];
      const b = (key) => base[mode === "dark" ? `dark-${key}` : key];
      const layers = { bg: n.bg, surface: n.surface, "surface-2": n["surface-2"] };
      for (const [layer, color] of Object.entries(layers)) {
        for (const text of ["text", "text-2", "text-muted"]) need(`${paletteId}.${mode} ${text}/${layer}`, n[text], color, 4.5);
        need(`${paletteId}.${mode} field-border/${layer}`, n["field-border"], color, 3);
      }
      const statuses = { positive: n.positive ?? b("positive"), negative: b("negative"), warning: b("warning"), info: b("info"), vip: b("vip") };
      for (const [status, color] of Object.entries(statuses)) {
        need(`${paletteId}.${mode} ${status}/surface`, color, n.surface, 4.5);
        need(`${paletteId}.${mode} ${status}/bg`, color, n.bg, 4.5);
      }
      for (const container of ["positive-container", "negative-container", "warning-container", "info-container"]) {
        need(`${paletteId}.${mode} text/${container}`, n.text, b(container), 4.5);
      }
      for (const series of ["chart-income", "chart-expense"]) need(`${paletteId}.${mode} ${series}/surface`, b(series), n.surface, 3);
      for (const [accentId, accentPair] of Object.entries(appearance.accents)) {
        const a = accentPair[mode];
        const where = `${paletteId}+${accentId}.${mode}`;
        need(`${where} tint/surface`, a.tint, n.surface, 4.5);
        need(`${where} tint/bg`, a.tint, n.bg, 4.5);
        need(`${where} tint/surface-2`, a.tint, n["surface-2"], 3);
        need(`${where} focus-ring/bg`, a["focus-ring"], n.bg, 3);
        need(`${where} focus-ring/surface`, a["focus-ring"], n.surface, 3);
        need(`${where} on-tint/tint`, a["on-tint"], a.tint, 4.5);
        need(`${where} on-tint/tint-pressed`, a["on-tint"], a["tint-pressed"], 4.5);
        need(`${where} on-tint-container/tint-container`, a["on-tint-container"], a["tint-container"], 4.5);
        need(`${where} text/tint-container`, n.text, a["tint-container"], 4.5);
        need(`${where} tint/tint-container`, a.tint, a["tint-container"], 3);
      }
    }
  }
  return failures;
}

const camel = (key) => key.replace(/[-_]([a-z0-9])/g, (_, c) => c.toUpperCase());
const hex = (value) => value.replace("#", "").toUpperCase();
const kotlinColor = (value) => `Color(0xFF${hex(value)})`;
const kotlinFloat = (value) => `${Number.isInteger(value) ? value.toFixed(1) : value}f`;
const swiftRgb = (value) => `0x${hex(value)}`;
const quote = (text) => JSON.stringify(text);

/** Pure-Kotlin catalog (core/data, no Compose): option ids, labels, defaults and the classic set. */
export function kotlinCatalog(a, designVersion) {
  const options = OPTION_KEYS.map((key) => {
    const o = a.options[key];
    const values = o.values.map((v) => `            AppearanceOptionValue(${quote(v.id)}, ${quote(v.es)}, ${quote(v.en)}${v.scale !== undefined ? `, scale = ${kotlinFloat(v.scale)}` : ""}),`).join("\n");
    return `        AppearanceOption(\n            key = ${quote(key)}, default = ${quote(o.default)}, classic = ${quote(o.classic)},\n            values = listOf(\n    ${values.replace(/\n {12}/g, "\n                ")}\n            ),\n        ),`;
  }).join("\n");
  return `// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR ${designVersion}) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
package com.dincr.data.generated

data class AppearanceOptionValue(val id: String, val es: String, val en: String, val scale: Float? = null)

data class AppearanceOption(val key: String, val default: String, val classic: String, val values: List<AppearanceOptionValue>) {
    fun has(id: String?) = values.any { it.id == id }
}

object AppearanceCatalog {
    const val VERSION = ${a.version}

    val options: List<AppearanceOption> = listOf(
${options}
    )

    fun option(key: String): AppearanceOption = options.first { it.key == key }
}
`;
}

/** Compose color/shape/density tokens per appearance option (core/design). */
export function kotlinTokens(a, designVersion) {
  const neutrals = (n) => {
    const fields = NEUTRALS.map((key) => `${camel(key)} = ${kotlinColor(n[key])}`);
    for (const key of NEUTRAL_EXTRAS) fields.push(`${camel(key)} = ${n[key] ? kotlinColor(n[key]) : "null"}`);
    return `AppearanceNeutrals(${fields.join(", ")})`;
  };
  const accent = (x) => `AppearanceAccent(${ACCENT.map((key) => `${camel(key)} = ${kotlinColor(x[key])}`).join(", ")})`;
  const palettes = Object.entries(a.palettes).map(([id, p]) => `        ${quote(id)} to AppearancePair(\n            light = ${neutrals(p.light)},\n            dark = ${neutrals(p.dark)},\n        ),`).join("\n");
  const accents = Object.entries(a.accents).map(([id, p]) => `        ${quote(id)} to AppearancePair(\n            light = ${accent(p.light)},\n            dark = ${accent(p.dark)},\n        ),`).join("\n");
  const shapes = Object.entries(a.shapes).map(([id, s]) => `        ${quote(id)} to AppearanceShape(card = ${s.card}.dp, control = ${s.control}.dp),`).join("\n");
  const density = Object.entries(a.density).map(([id, d]) => `        ${quote(id)} to AppearanceDensity(gap = ${d.gap}.dp, cardPadding = ${d.cardPadding}.dp, rowMin = ${d.rowMin}.dp),`).join("\n");
  return `// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR ${designVersion}) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
package com.dincr.design.generated

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

data class AppearancePair<T>(val light: T, val dark: T) {
    fun pick(dark: Boolean): T = if (dark) this.dark else light
}

data class AppearanceNeutrals(
    val bg: Color, val surface: Color, val surface2: Color, val line: Color, val lineStrong: Color, val fieldBorder: Color,
    val text: Color, val text2: Color, val textMuted: Color, val positive: Color?, val glow: Color?,
)

data class AppearanceAccent(val tint: Color, val tintPressed: Color, val tintContainer: Color, val onTint: Color, val onTintContainer: Color, val focusRing: Color)

data class AppearanceShape(val card: Dp, val control: Dp)

data class AppearanceDensity(val gap: Dp, val cardPadding: Dp, val rowMin: Dp)

object DincrAppearanceTokens {
    val palettes: Map<String, AppearancePair<AppearanceNeutrals>> = linkedMapOf(
${palettes}
    )

    val accents: Map<String, AppearancePair<AppearanceAccent>> = linkedMapOf(
${accents}
    )

    val shapes: Map<String, AppearanceShape> = linkedMapOf(
${shapes}
    )

    val density: Map<String, AppearanceDensity> = linkedMapOf(
${density}
    )
}
`;
}

/** Swift catalog (DincrCore, Foundation only): option ids, labels, defaults and the classic set. */
export function swiftCatalog(a, designVersion) {
  const options = OPTION_KEYS.map((key) => {
    const o = a.options[key];
    const values = o.values.map((v) => `                AppearanceOptionValue(id: ${quote(v.id)}, es: ${quote(v.es)}, en: ${quote(v.en)}${v.scale !== undefined ? `, scale: ${v.scale}` : ""}),`).join("\n");
    return `        AppearanceOption(\n            key: ${quote(key)}, defaultValue: ${quote(o.default)}, classic: ${quote(o.classic)},\n            values: [\n${values}\n            ]\n        ),`;
  }).join("\n");
  return `// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR ${designVersion}) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
import Foundation

public struct AppearanceOptionValue: Sendable, Equatable {
    public let id: String
    public let es: String
    public let en: String
    public let scale: Double?

    public init(id: String, es: String, en: String, scale: Double? = nil) {
        self.id = id; self.es = es; self.en = en; self.scale = scale
    }
}

public struct AppearanceOption: Sendable, Equatable {
    public let key: String
    public let defaultValue: String
    public let classic: String
    public let values: [AppearanceOptionValue]

    public func has(_ id: String?) -> Bool { values.contains { $0.id == id } }
}

public enum AppearanceCatalog {
    public static let version = ${a.version}

    public static let options: [AppearanceOption] = [
${options}
    ]

    public static func option(_ key: String) -> AppearanceOption? { options.first { $0.key == key } }
}
`;
}

/** SwiftUI color tokens per appearance option (DincrDesign). */
export function swiftTokens(a, designVersion) {
  const pair = (light, dark) => `Color(light: ${swiftRgb(light)}, dark: ${swiftRgb(dark)})`;
  const optionalPair = (light, dark) => (light && dark ? pair(light, dark) : "nil");
  const palettes = Object.entries(a.palettes).map(([id, p]) => {
    const fields = NEUTRALS.map((key) => `${camel(key)}: ${pair(p.light[key], p.dark[key])}`);
    for (const key of NEUTRAL_EXTRAS) fields.push(`${camel(key)}: ${optionalPair(p.light[key], p.dark[key])}`);
    return `        ${quote(id)}: AppearanceNeutrals(\n            ${fields.join(",\n            ")}\n        ),`;
  }).join("\n");
  const accents = Object.entries(a.accents).map(([id, p]) =>
    `        ${quote(id)}: AppearanceAccent(\n            ${ACCENT.map((key) => `${camel(key)}: ${pair(p.light[key], p.dark[key])}`).join(",\n            ")}\n        ),`).join("\n");
  const shapes = Object.entries(a.shapes).map(([id, s]) => `        ${quote(id)}: AppearanceShape(card: ${s.card}, control: ${s.control}),`).join("\n");
  const density = Object.entries(a.density).map(([id, d]) => `        ${quote(id)}: AppearanceDensity(gap: ${d.gap}, cardPadding: ${d.cardPadding}, rowMin: ${d.rowMin}),`).join("\n");
  return `// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR ${designVersion}) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
import SwiftUI

public struct AppearanceNeutrals: Sendable {
    public let bg, surface, surface2, line, lineStrong, fieldBorder, text, text2, textMuted: Color
    public let positive, glow: Color?
}

public struct AppearanceAccent: Sendable {
    public let tint, tintPressed, tintContainer, onTint, onTintContainer, focusRing: Color
}

public struct AppearanceShape: Sendable {
    public let card, control: CGFloat
}

public struct AppearanceDensity: Sendable {
    public let gap, cardPadding, rowMin: CGFloat
}

public enum DincrAppearanceTokens {
    public static let palettes: [String: AppearanceNeutrals] = [
${palettes}
    ]

    public static let accents: [String: AppearanceAccent] = [
${accents}
    ]

    public static let shapes: [String: AppearanceShape] = [
${shapes}
    ]

    public static let density: [String: AppearanceDensity] = [
${density}
    ]
}
`;
}

