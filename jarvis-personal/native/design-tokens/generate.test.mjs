// Tests for generate.mjs: node --test jarvis-personal/native/design-tokens/generate.test.mjs
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { contrast, contrastFailures, parseAppearance } from "./appearance.mjs";
import { appSources, checkedAppearance, colorMap, missingReferences, parseTokens, render } from "./generate.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const design = fs.readFileSync(path.join(repoRoot, "DESIGN.md"), "utf8").replace(/\r\n/g, "\n");
const appearanceSource = fs.readFileSync(path.join(here, "appearance.json"), "utf8");
const outputs = {
  swift: "jarvis-personal/native/ios/DincrKit/Sources/DincrDesign/Generated/DincrTokens.swift",
  kotlin: "jarvis-personal/native/android/core/design/src/main/kotlin/com/dincr/design/generated/DincrTokens.kt",
  swiftAppearance: "jarvis-personal/native/ios/DincrKit/Sources/DincrDesign/Generated/DincrAppearanceTokens.swift",
  swiftCatalog: "jarvis-personal/native/ios/DincrKit/Sources/DincrCore/Generated/AppearanceCatalog.swift",
  kotlinAppearance: "jarvis-personal/native/android/core/design/src/main/kotlin/com/dincr/design/generated/DincrAppearanceTokens.kt",
  kotlinCatalog: "jarvis-personal/native/android/core/data/src/main/kotlin/com/dincr/data/generated/AppearanceCatalog.kt",
};
const edit = (from, to) => {
  assert.ok(design.includes(from), `fixture edit not applicable: ${from}`);
  return design.replace(from, to);
};

test("deterministic and independent of line endings", () => {
  assert.deepEqual(render(design), render(design));
  assert.deepEqual(render(design.replace(/\n/g, "\r\n")), render(design));
});

test("the committed outputs are what DESIGN.md renders", () => {
  const rendered = render(design);
  for (const [kind, file] of Object.entries(outputs)) {
    assert.equal(fs.readFileSync(path.join(repoRoot, file), "utf8").replace(/\r\n/g, "\n"), rendered[kind], file);
  }
});

test("malformed DESIGN.md fails instead of dropping tokens", () => {
  const cases = {
    "unparsable entry": edit('  tint: "#0B6E68"', "  tint: #0B6E68"),
    "unparsable scale entry": edit('  "4": "16px"', '  "4": 16px'),
    "px value that is not a size": edit('  "4": "16px"', '  "4": "0x10px"'),
    "negative px value": edit('  "4": "16px"', '  "4": "-16px"'),
    "version that is not semver": design.replace(/^version:.*$/m, 'version: 2.0.0"; evil()'),
    "not #RRGGBB": edit('  tint: "#0B6E68"', '  tint: "teal"'),
    "duplicate token": edit('  tint: "#0B6E68"', '  tint: "#0B6E68"\n  tint: "#0B6E69"'),
    "missing dark counterpart": edit('  dark-tint: "#3CCFBF"\n', ""),
    "orphan dark token": edit('  dark-tint: "#3CCFBF"', '  dark-tint: "#3CCFBF"\n  dark-extra: "#000000"'),
    "missing version": design.replace(/^version:.*\n/m, ""),
    "missing block": design.replace(/^spacing:/m, "spacingx:"),
  };
  for (const [name, source] of Object.entries(cases)) {
    assert.notEqual(source, design, name);
    assert.throws(() => parseTokens(source), Error, name);
  }
});

test("a token the apps use cannot disappear", () => {
  const tokens = parseTokens(design);
  assert.deepEqual(missingReferences(tokens, appSources()), [], "the current apps only use defined tokens");
  assert.deepEqual(
    missingReferences(tokens, ["DincrColor.tint DincrColor.retired DincrSpacing.s99 DincrColors.textMuted DincrRadius.huge DincrIconSize.md"]),
    ["DincrColor.retired", "DincrRadius.huge", "DincrSpacing.s99"],
  );
});

test("--check reports drift and never writes; the generator fixes it", () => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-tokens-"));
  try {
    const copy = (relative) => {
      fs.mkdirSync(path.dirname(path.join(sandbox, relative)), { recursive: true });
      fs.copyFileSync(path.join(repoRoot, relative), path.join(sandbox, relative));
    };
    const script = "jarvis-personal/native/design-tokens/generate.mjs";
    const companions = ["jarvis-personal/native/design-tokens/appearance.mjs", "jarvis-personal/native/design-tokens/appearance.json"];
    [script, ...companions, "DESIGN.md", ...Object.values(outputs)].forEach(copy);
    const run = (...args) => spawnSync(process.execPath, [path.join(sandbox, script), ...args], { encoding: "utf8" });
    const snapshot = () => Object.values(outputs).map((file) => fs.readFileSync(path.join(sandbox, file), "utf8"));

    assert.equal(run("--check").status, 0);
    // A token outside the classic appearance set (changing the tint alone would also, rightly,
    // fail the classic-appearance check).
    fs.writeFileSync(path.join(sandbox, "DESIGN.md"), edit('  vip: "#8A5A00"', '  vip: "#8A5A01"'));
    const before = snapshot();
    const stale = run("--check");
    assert.equal(stale.status, 1, "drift must fail --check");
    assert.match(stale.stderr, /stale/);
    assert.deepEqual(snapshot(), before, "--check must not modify the generated files");
    execFileSync(process.execPath, [path.join(sandbox, script)]);
    assert.notDeepEqual(snapshot(), before);
    assert.equal(run("--check").status, 0);
  } finally {
    fs.rmSync(sandbox, { recursive: true, force: true });
  }
});

// Personal appearance (appearance.json, Owner only in phase 1).

const appearance = () => JSON.parse(appearanceSource);
const tokens = parseTokens(design);

test("the classic appearance is exactly DESIGN.md, so accounts on it see today's app", () => {
  const a = checkedAppearance(tokens, appearanceSource);
  const base = colorMap(tokens);
  const palette = a.palettes[a.options.palette.classic];
  const accent = a.accents[a.options.accent.classic];
  for (const [key, value] of Object.entries({ ...palette.light, ...accent.light })) assert.equal(value, base[key], key);
  for (const [key, value] of Object.entries({ ...palette.dark, ...accent.dark })) assert.equal(value, base[`dark-${key}`], `dark-${key}`);
  assert.equal(a.options.surfaces.classic, "tonal");
  assert.deepEqual(a.shapes.tonal, { card: 20, control: 14 }, "tonal shapes are DESIGN.md rounded.lg / rounded.md");
  assert.deepEqual(a.density.comfortable, { gap: 16, cardPadding: 16, rowMin: 56 }, "comfortable density is DESIGN.md spacing");
  const drifted = appearance();
  drifted.palettes.clasico.light.text = "#0B1527";
  assert.throws(() => checkedAppearance(tokens, drifted), /classic palette light.text/);
});

test("the Owner default is the iOS Owner identity (OwnerTheme.swift), so both apps agree", () => {
  const owner = fs.readFileSync(path.join(here, "../ios/DincrKit/Sources/DincrDesign/Owner/OwnerTheme.swift"), "utf8");
  const ownerColor = (name) => {
    const m = owner.match(new RegExp(`static let ${name} = Color\\(light: 0x([0-9A-F]{6}), dark: 0x([0-9A-F]{6})\\)`));
    assert.ok(m, `OwnerColor.${name} not found`);
    return { light: `#${m[1]}`, dark: `#${m[2]}` };
  };
  const a = parseAppearance(appearanceSource);
  const palette = a.palettes[a.options.palette.default];
  const accent = a.accents[a.options.accent.default];
  const pairs = {
    surface: [palette, "surface"], surface2: [palette, "surface-2"], border: [palette, "line"],
    text: [palette, "text"], text2: [palette, "text-2"], textMuted: [palette, "text-muted"], positive: [palette, "positive"],
    backgroundMiddle: [palette, "bg"], backgroundCenter: [palette, "glow"],
    accent: [accent, "tint"], accentActive: [accent, "tint-pressed"], onAccent: [accent, "on-tint"],
    accentContainer: [accent, "tint-container"], onAccentContainer: [accent, "on-tint-container"],
  };
  for (const [name, [set, key]] of Object.entries(pairs)) {
    const ios = ownerColor(name);
    assert.equal(set.light[key], ios.light, `${name} light`);
    assert.equal(set.dark[key], ios.dark, `${name} dark`);
  }
  assert.equal(a.options.surfaces.default, "outlined", "the Owner identity has a hairline border");
});

test("every palette x accent x scheme keeps the contrast rules, and a weak color is caught", () => {
  const base = colorMap(tokens);
  assert.deepEqual(contrastFailures(parseAppearance(appearanceSource), base), []);
  const weak = appearance();
  weak.palettes.arena.light["text-muted"] = "#A39A8E";
  weak.accents.ciruela.dark["on-tint"] = "#9A7AB0";
  const failures = contrastFailures(parseAppearance(weak), base);
  assert.ok(failures.some((f) => f.startsWith("arena.light text-muted/")), failures.join("; "));
  assert.ok(failures.some((f) => f.includes("+ciruela.dark on-tint/tint")), failures.join("; "));
  assert.throws(() => checkedAppearance(tokens, weak), /contrast/);
  assert.equal(contrast("#000000", "#FFFFFF").toFixed(1), "21.0");
});

test("malformed appearance.json fails instead of dropping options", () => {
  const cases = {
    "unknown default": (a) => { a.options.palette.default = "neon"; },
    "palette without its option": (a) => { a.palettes.neon = a.palettes.arena; },
    "missing dark token": (a) => { delete a.accents.tinta.dark.tint; },
    "unknown token": (a) => { a.palettes.grafito.light.glare = "#FFFFFF"; },
    "half-defined override": (a) => { delete a.palettes.oceano.light.positive; },
    "not #RRGGBB": (a) => { a.accents.cian.light.tint = "blue"; },
    "missing label": (a) => { delete a.options.density.values.compact.en; },
    "text scale out of range": (a) => { a.options.text_size.values.xl.scale = 3; },
    "touch target below 48px": (a) => { a.density.compact["row-min"] = "40px"; },
    "wrong version": (a) => { a.version = 2; },
  };
  for (const [name, mutate] of Object.entries(cases)) {
    const a = appearance();
    mutate(a);
    assert.throws(() => parseAppearance(a), Error, name);
  }
});
