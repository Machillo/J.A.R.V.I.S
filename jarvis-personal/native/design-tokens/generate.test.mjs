// Tests for generate.mjs: node --test jarvis-personal/native/design-tokens/generate.test.mjs
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { appSources, missingReferences, parseTokens, render } from "./generate.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const design = fs.readFileSync(path.join(repoRoot, "DESIGN.md"), "utf8").replace(/\r\n/g, "\n");
const outputs = {
  swift: "jarvis-personal/native/ios/DincrKit/Sources/DincrDesign/Generated/DincrTokens.swift",
  kotlin: "jarvis-personal/native/android/core/design/src/main/kotlin/com/dincr/design/generated/DincrTokens.kt",
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
    [script, "DESIGN.md", ...Object.values(outputs)].forEach(copy);
    const run = (...args) => spawnSync(process.execPath, [path.join(sandbox, script), ...args], { encoding: "utf8" });
    const snapshot = () => Object.values(outputs).map((file) => fs.readFileSync(path.join(sandbox, file), "utf8"));

    assert.equal(run("--check").status, 0);
    fs.writeFileSync(path.join(sandbox, "DESIGN.md"), edit('  tint: "#0B6E68"', '  tint: "#0B6E69"'));
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
