// Tests for the store-asset pipeline (no browser needed).
//   node --test jarvis-personal/store-assets/scripts/
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import zlib from "node:zlib";
import { fill, finalGateProblems, loadCopy, loadScreens, loadTargets } from "./compose.mjs";
import { decodePng, encodeRgbPng, flattenToRgb, pngInfo } from "./png.mjs";
import { copyProblems, imageProblems } from "./validate.mjs";

const targetsConfig = loadTargets();
const screens = loadScreens();

function rgbaPng(width, height, [r, g, b, a]) {
  // Hand-built RGBA PNG (filter 0 on every row) to exercise the decoder independently of the encoder.
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(width * 4).fill(Buffer.from([r, g, b, a]))]);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  const chunk = (type, data) => {
    const head = Buffer.alloc(8); head.writeUInt32BE(data.length); head.write(type, 4, "latin1");
    return Buffer.concat([head, data, Buffer.alloc(4)]); // CRC is not checked by the reader
  };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(width); ihdr.writeUInt32BE(height, 4); ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

test("an RGBA render is flattened onto the background and re-encoded without alpha", () => {
  const source = rgbaPng(4, 3, [255, 0, 0, 128]);
  assert.equal(pngInfo(source).alpha, true);
  const flat = flattenToRgb(decodePng(source), [0, 0, 255]);
  const out = encodeRgbPng(flat);
  const info = pngInfo(out);
  assert.deepEqual([info.width, info.height, info.colorType, info.alpha], [4, 3, 2, false]);
  const pixels = decodePng(out).pixels;
  assert.deepEqual([...pixels.subarray(0, 3)], [128, 0, 127]); // 50% red over blue
});

test("a tRNS chunk counts as transparency", () => {
  const png = encodeRgbPng({ width: 1, height: 1, pixels: Buffer.from([1, 2, 3]) });
  const iend = png.length - 12;
  const trns = Buffer.from([0, 0, 0, 6, 0x74, 0x52, 0x4e, 0x53, 0, 1, 0, 2, 0, 3, 0, 0, 0, 0]);
  const withTrns = Buffer.concat([png.subarray(0, iend), trns, png.subarray(iend)]);
  assert.equal(pngInfo(withTrns).alpha, true);
});

test("copy is escaped into templates and a missing placeholder fails loudly", () => {
  assert.equal(fill("<h1>{{title}}</h1>", { title: "<script>x</script> & \"q\"" }), "<h1>&lt;script&gt;x&lt;/script&gt; &amp; &quot;q&quot;</h1>");
  assert.throws(() => fill("{{title}} {{subtitle}}", { title: "a" }), /subtitle/);
});

test("the final run is refused while the #287 gate is closed, screens are unconfirmed or captures are missing", () => {
  const rawDir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-raw-"));
  const phone = targetsConfig.targets.filter((t) => t.id === "google-phone");
  const problems = finalGateProblems({ screens, targets: phone, locales: screens.locales, rawDir, sourceCommit: "abc", isOnMain: () => false });
  assert.ok(problems.some((p) => p.includes("release gate closed")));
  assert.ok(problems.some((p) => p.includes("not on origin/main")));
  assert.ok(problems.some((p) => p.includes("no screen is confirmed")));
  assert.ok(problems.some((p) => p.includes("capture manifest")));

  // Gate open, one confirmed screen, commit on main, manifest present: only the missing capture remains.
  const open = { ...screens, release_gate: { ...screens.release_gate, status: "released" }, screens: [{ ...screens.screens[0], confirmed: true }] };
  fs.mkdirSync(path.join(rawDir, "android"), { recursive: true });
  fs.writeFileSync(path.join(rawDir, "android", "capture-manifest.json"), JSON.stringify({ source_commit: "abc" }));
  const remaining = finalGateProblems({ screens: open, targets: phone, locales: [screens.locales[0]], rawDir, sourceCommit: "abc", isOnMain: () => true });
  assert.match(remaining[0], /missing capture .*01-home\.png$/);
  assert.equal(remaining.length, 1);

  fs.mkdirSync(path.join(rawDir, "android", "es", "phone"), { recursive: true });
  fs.writeFileSync(path.join(rawDir, "android", "es", "phone", "01-home.png"), encodeRgbPng({ width: 1, height: 1, pixels: Buffer.from([0, 0, 0]) }));
  assert.deepEqual(finalGateProblems({ screens: open, targets: phone, locales: [screens.locales[0]], rawDir, sourceCommit: "abc", isOnMain: () => true }), []);
  fs.rmSync(rawDir, { recursive: true, force: true });
});

test("the shipped copy passes the store copy rules, and banned phrases are caught", () => {
  const copies = Object.fromEntries(screens.locales.map((l) => [l.id, loadCopy(l.id)]));
  assert.deepEqual(copyProblems(targetsConfig, screens, copies), []);
  const bad = structuredClone(copies);
  bad.es.screens.home.title = "La mejor app: descargá ahora";
  bad.en.screens.home.subtitle = "The #1 budget app";
  const problems = copyProblems(targetsConfig, screens, bad);
  assert.ok(problems.some((p) => p.includes('"mejor"')));
  assert.ok(problems.some((p) => p.includes('"#1"')));
  // Whole words only: "newsletter" or "topic" must not trip "new"/"top".
  bad.en.screens.home.subtitle = "Topics and newsletters";
  assert.ok(!copyProblems(targetsConfig, screens, bad).some((p) => p.includes('"new"') || p.includes('"top"')));
});

function writeImage(dir, target, locale, name, { width = target.width, height = target.height, meta = {}, alpha = false } = {}) {
  const folder = path.join(dir, target.store, locale, target.id);
  fs.mkdirSync(folder, { recursive: true });
  const png = alpha ? rgbaPng(width, height, [0, 0, 0, 255]) : encodeRgbPng({ width, height, pixels: Buffer.alloc(width * height * 3) });
  fs.writeFileSync(path.join(folder, `${name}.png`), png);
  fs.writeFileSync(path.join(folder, `${name}.json`), JSON.stringify({ mode: "final", caption_ratio: 0.15, capture: { placeholder: false }, source_commit: "abc", ...meta }));
}

test("the validator rejects wrong sizes, alpha, a caption band over 20%, previews and placeholders", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  const phone = targetsConfig.targets.find((t) => t.id === "google-phone");
  const only = { ...targetsConfig, targets: [phone] };
  for (const n of ["01", "02", "03", "04"]) writeImage(dir, phone, "es-419", n);
  assert.deepEqual(imageProblems(dir, only), []);

  writeImage(dir, phone, "es-419", "05", { width: 1080, height: 1920 });
  writeImage(dir, phone, "es-419", "06", { alpha: true });
  writeImage(dir, phone, "es-419", "07", { meta: { caption_ratio: 0.23 } });
  writeImage(dir, phone, "es-419", "08", { meta: { mode: "preview", capture: { placeholder: true }, source_commit: null } });
  const problems = imageProblems(dir, only).join("\n");
  assert.match(problems, /05\.png: 1080x1920, expected 1440x2560/);
  assert.match(problems, /06\.png: has an alpha channel/);
  assert.match(problems, /07\.png: caption band 23\.0% > 20%/);
  assert.match(problems, /08\.png: is a preview image/);
  assert.match(problems, /08\.png: built from a placeholder/);
  assert.equal(imageProblems(dir, only, { allowPreview: true }).some((p) => p.includes("08.png")), false);

  writeImage(dir, phone, "es-419", "09");
  assert.match(imageProblems(dir, only).join("\n"), /9 images, the store accepts at most 8/);
  fs.rmSync(dir, { recursive: true, force: true });
});
