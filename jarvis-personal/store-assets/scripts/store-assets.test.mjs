// Tests for the store-asset pipeline (no browser, emulator or simulator needed).
//   node --test jarvis-personal/store-assets/scripts/store-assets.test.mjs
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import zlib from "node:zlib";
import { DEMO_MODE, instrumentPassed } from "./capture-android.mjs";
import { DEVICES, STATUS_BAR } from "./capture-ios.mjs";
import { appCommitProblems, fill, finalGateProblems, loadCopy, loadScreens, loadTargets, portableHtml, renderStable, root, screensFor } from "./compose.mjs";
import { pathToFileURL } from "node:url";
import { decodePng, encodeRgbPng, flattenToRgb, pngInfo } from "./png.mjs";
import { copyProblems, imageProblems } from "./validate.mjs";

const targetsConfig = loadTargets();
const screens = loadScreens();
const target = (id) => targetsConfig.targets.find((t) => t.id === id);
const BASELINE = screens.app_baseline.merge_commit;
const AFTER = "a".repeat(40); // a commit on main that contains #287
const BEFORE = "b".repeat(40); // a commit on main from before #287 (Capacitor UI)
const BRANCH = "e".repeat(40); // a reviewed branch commit after #287, not merged yet
/** Fake git: AFTER, BEFORE and BASELINE are on main; BRANCH only in HEAD; AFTER and BRANCH contain BASELINE. */
const isAncestor = (ancestor, descendant) => {
  if (descendant === "origin/main") return [AFTER, BEFORE, BASELINE].includes(ancestor);
  if (descendant === "HEAD") return [AFTER, BEFORE, BASELINE, BRANCH].includes(ancestor);
  if (ancestor === BASELINE) return [AFTER, BASELINE, BRANCH].includes(descendant);
  return ancestor === descendant;
};
const sha = (buffer) => crypto.createHash("sha256").update(buffer).digest("hex");
const tinyPng = (bytes = [0, 0, 0]) => encodeRgbPng({ width: 1, height: 1, pixels: Buffer.from(bytes) });

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
  const png = tinyPng([1, 2, 3]);
  const iend = png.length - 12;
  const trns = Buffer.from([0, 0, 0, 6, 0x74, 0x52, 0x4e, 0x53, 0, 1, 0, 2, 0, 3, 0, 0, 0, 0]);
  const withTrns = Buffer.concat([png.subarray(0, iend), trns, png.subarray(iend)]);
  assert.equal(pngInfo(withTrns).alpha, true);
});

test("copy is escaped into templates and a missing placeholder fails loudly", () => {
  assert.equal(fill("<h1>{{title}}</h1>", { title: "<script>x</script> & \"q\"" }), "<h1>&lt;script&gt;x&lt;/script&gt; &amp; &quot;q&quot;</h1>");
  assert.throws(() => fill("{{title}} {{subtitle}}", { title: "a" }), /subtitle/);
});

test("a render is kept only when two consecutive renders are identical (no paint glitches)", () => {
  const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "dincr-render-")), "r.png");
  const drawing = (frames) => { let n = 0; return () => { fs.writeFileSync(out, tinyPng(frames[n++])); return { frame: n }; }; };
  // A clean frame, a glitched one, then the clean frame twice: accepted on the 4th render.
  assert.deepEqual(renderStable(null, "x.html", out, 1, 1, 4, drawing([[1, 1, 1], [255, 255, 255], [1, 1, 1], [1, 1, 1]])), { frame: 4 });
  assert.deepEqual([...decodePng(fs.readFileSync(out)).pixels], [1, 1, 1]);
  assert.throws(() => renderStable(null, "x.html", out, 1, 1, 4, drawing([[1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4]])), /did not render the same way twice/);
});

test("the saved HTML source links into the repo relatively, never through a local path", () => {
  const base = path.resolve("/work/repo");
  const out = path.join(base, "jarvis-personal/store-assets/output/final/google/es-419/google-phone/01-home.png");
  const html = `<img src="${pathToFileURL(path.join(base, "jarvis-personal/store-assets/raw/android/es/phone/01-home.png")).href}">`;
  assert.equal(portableHtml(html, out, base), '<img src="../../../../../../../jarvis-personal/store-assets/raw/android/es/phone/01-home.png">');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  writeImage(dir, target("google-phone"), "es-419", "01");
  fs.writeFileSync(path.join(dir, "google/es-419/google-phone/01-home.html"), '<img src="file:///C:/Users/someone/x.png">');
  assert.match(validator(dir, [target("google-phone")]).join("\n"), /01-home\.png: its \.html source links to a local file:\/\/ path/);
});

// --- screen list ---------------------------------------------------------------------------------

test("the screen list only confirms screens the native apps have, with how to reach them", () => {
  assert.ok(/^[0-9a-f]{40}$/.test(BASELINE));
  const ids = screens.screens.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(!ids.some((id) => id.includes("accounts")), "the native apps have no accounts screen");
  for (const screen of screens.screens) {
    assert.ok(["free", "basic", "vip"].includes(screen.plan), `${screen.id}: plan`);
    for (const [platform, entry] of Object.entries(screen.platforms)) {
      assert.ok(["android", "ios"].includes(platform));
      if (entry.confirmed) {
        assert.equal(entry.available, true, `${screen.id}/${platform}: confirmed but not available`);
        assert.ok(entry.how_to_reach, `${screen.id}/${platform}: confirmed without how_to_reach`);
      } else {
        assert.ok(entry.reason, `${screen.id}/${platform}: unconfirmed without a reason`);
      }
    }
  }
  // Finals use only confirmed screens; previews show every available one (as labelled placeholders).
  const pending = { ...screens, screens: [{ id: "x", plan: "free", platforms: { android: { available: true, confirmed: false, reason: "not checked" } } }] };
  assert.deepEqual(screensFor(pending, target("google-phone"), true), []);
  assert.equal(screensFor(pending, target("google-phone"), false).length, 1);
  // Google Play takes at most 8. Since #294 the iOS app has every store screen (Home VIP, budget,
  // strategy, Email Monitor included), with the same ids and plans as Android.
  assert.ok(screensFor(screens, target("google-phone"), true).length <= 8);
  const ids8 = ["01-home", "02-overview", "03-movements", "04-debts", "05-goals", "06-budget", "07-strategy", "08-mail"];
  assert.deepEqual(screensFor(screens, target("apple-iphone-69"), true).map((s) => s.id), ids8);
  assert.deepEqual(screensFor(screens, target("google-phone"), true).map((s) => s.id), ids8);
});

test("the capture tests navigate to exactly the confirmed screens, each with the screen's plan", () => {
  const kotlin = fs.readFileSync(path.join(root, "../native/android/app/src/androidTest/kotlin/com/dincr/app/StoreScreenshots.kt"), "utf8");
  const captured = [...kotlin.matchAll(/launch\("(\w+)"\)[\s\S]*?capture\("([\w-]+)"\)/g)].map(([, plan, id]) => ({ id, plan }));
  const android = screensFor(screens, target("google-phone"), true).map((s) => ({ id: s.id, plan: s.plan }));
  assert.deepEqual(captured, android);
  assert.match(kotlin, /assumeTrue\(InstrumentationRegistry\.getArguments\(\)\.getString\("storeScreenshots"\) == "true"\)/);
  assert.match(kotlin, /"dincrFixtures", "STORE"/);

  const swift = fs.readFileSync(path.join(root, "../native/ios/DINCRUITests/StoreScreenshots.swift"), "utf8");
  const ios = [...swift.matchAll(/shoot\("([\w-]+)", plan: "(\w+)"\)/g)].map(([, id, plan]) => ({ id, plan }));
  assert.deepEqual(ios, screensFor(screens, target("apple-iphone-69"), true).map((s) => ({ id: s.id, plan: s.plan })));
  assert.match(swift, /"-DincrFixtures", "store"/);
  assert.match(swift, /"-DincrPlan", plan/); // each iOS screen runs with its own plan
  assert.match(swift, /XCTSkipIf\(dir\.isEmpty/);
});

test("the iOS capture run uses simulators of the exact App Store sizes and a clean status bar", () => {
  assert.equal(DEVICES.phone.target, "apple-iphone-69");
  assert.equal(DEVICES.tablet.target, "apple-ipad-13");
  const bar = STATUS_BAR.join(" ");
  assert.match(bar, /--time 9:41/);
  assert.match(bar, /--batteryLevel 100/);
});

test("the Android capture run cleans the status bar and requires every test to pass", () => {
  const commands = DEMO_MODE.map((c) => c.join(" "));
  assert.ok(commands.includes("network -e mobile hide"));
  assert.ok(commands.includes("notifications -e visible false"));
  assert.ok(commands.some((c) => c.startsWith("clock -e hhmm 0941")));
  assert.equal(instrumentPassed("com.dincr.app.StoreScreenshots:........\n\nOK (8 tests)", 8), true);
  assert.equal(instrumentPassed("OK (0 tests)", 8), false); // opt-in argument missing: everything skipped
  assert.equal(instrumentPassed("FAILURES!!!\nTests run: 8,  Failures: 1", 8), false);
  assert.equal(instrumentPassed("OK (7 tests)", 8), false);
});

// --- final gate ----------------------------------------------------------------------------------

/** A raw/ tree with one confirmed Android screen captured correctly for `es`. */
function rawTree({ manifest = {}, record = {} } = {}) {
  const rawDir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-raw-"));
  const phone = path.join(rawDir, "android", "es", "phone");
  fs.mkdirSync(phone, { recursive: true });
  const png = tinyPng();
  fs.writeFileSync(path.join(phone, "02-overview.png"), png);
  fs.writeFileSync(path.join(rawDir, "android", "capture-manifest.json"), JSON.stringify({
    platform: "android", fixture: "STORE", source_commit: AFTER, source_dirty: false, built: true,
    captures: [{ id: "02-overview", locale: "es", plan: "free", file: "raw/android/es/phone/02-overview.png", sha256: sha(png), ...record }],
    ...manifest,
  }));
  return rawDir;
}
const oneScreen = { ...screens, screens: screens.screens.filter((s) => s.id === "02-overview") };
const gate = (rawDir, sourceCommit = AFTER, extra = {}) => finalGateProblems({
  screens: oneScreen, targets: [target("google-phone")], locales: [screens.locales[0]], rawDir, sourceCommit, isAncestor, changedSince: () => false, ...extra,
});

test("the final run accepts a clean post-#287 capture that matches its manifest", () => {
  assert.deepEqual(gate(rawTree()), []);
});

test("iOS finals need an app commit that contains #294 (before it the iOS app was a prototype)", () => {
  const ios = screens.platform_baselines.ios;
  assert.equal(ios.pr, 294);
  assert.equal(screens.platform_baselines.android.merge_commit, BASELINE);
  const iphone = { targets: [target("apple-iphone-69")], screens };
  // AFTER contains #287 but not #294 in the fake history: refused for iOS, not for Android.
  assert.ok(gate(rawTree(), AFTER, iphone).some((p) => p.includes("predates the ios store screens (PR #294")));
  assert.ok(!gate(rawTree(), AFTER).some((p) => p.includes("predates the android store screens")));
  const withIos = (a, d) => (a === ios.merge_commit && d === AFTER) || isAncestor(a, d);
  assert.ok(!gate(rawTree(), AFTER, { ...iphone, isAncestor: withIos }).some((p) => p.includes("predates the ios store screens")));
});

test("the final run refuses a capture from before #287 (Capacitor UI), off main, or without a commit", () => {
  const rawDir = rawTree({ manifest: { source_commit: BEFORE } });
  assert.ok(gate(rawDir, BEFORE).some((p) => p.includes("predates the native app")));
  assert.ok(gate(rawTree({ manifest: { source_commit: "c".repeat(40) } }), "c".repeat(40)).some((p) => p.includes("not in the checked-out history")));
  // A branch capture is fine for review; the pre-upload check (--require-main) wants it merged.
  const branch = rawTree({ manifest: { source_commit: BRANCH } });
  assert.deepEqual(gate(branch, BRANCH), []);
  assert.ok(gate(branch, BRANCH, { requireMain: true }).some((p) => p.includes("is not on origin/main")));
  assert.deepEqual(gate(rawTree(), AFTER, { requireMain: true }), []);
  assert.ok(gate(rawTree(), null).some((p) => p.includes("--source-commit is required")));
  assert.deepEqual(appCommitProblems(AFTER, screens, isAncestor, { changedSince: () => false }), []);
  assert.ok(appCommitProblems(AFTER, { ...screens, app_baseline: {} }, isAncestor, { changedSince: () => false }).some((p) => p.includes("no app_baseline")));
});

test("the final run refuses unconfirmed platforms, dirty or foreign manifests and changed captures", () => {
  const iosUnconfirmed = { ...screens.screens[0], platforms: { ...screens.screens[0].platforms, ios: { available: false, confirmed: false, reason: "not checked" } } };
  assert.ok(gate(rawTree(), AFTER, { targets: [target("apple-iphone-69")], screens: { ...oneScreen, screens: [iosUnconfirmed] } })
    .some((p) => p.includes("no screen is confirmed for ios")));
  assert.ok(gate(rawTree({ manifest: { source_dirty: true } })).some((p) => p.includes("uncommitted changes")));
  assert.ok(gate(rawTree({ manifest: { fixture: "POPULATED" } })).some((p) => p.includes("fixture POPULATED")));
  assert.ok(gate(rawTree({ manifest: { source_commit: "d".repeat(40) } })).some((p) => p.includes("from another commit")));
  assert.ok(gate(rawTree({ record: { sha256: "0".repeat(64) } })).some((p) => p.includes("changed after capture")));
  assert.ok(gate(rawTree({ record: { plan: "vip" } })).some((p) => p.includes("captured with plan vip")));
  assert.ok(gate(rawTree({ manifest: { captures: [] } })).some((p) => p.includes("is not in")));
  // --no-build: the installed app may come from anywhere.
  assert.ok(gate(rawTree({ manifest: { built: false } })).some((p) => p.includes("did not build the app")));
  // The app changed after the capture: stale.
  assert.ok(gate(rawTree(), AFTER, { changedSince: (commit, paths) => paths.includes("jarvis-personal/native") }).some((p) => p.includes("changed after")));
  // A tablet record never stands in for the phone capture of the same screen.
  const tabletOnly = rawTree();
  const manifestFile = path.join(tabletOnly, "android", "capture-manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestFile, "utf8"));
  manifest.captures = manifest.captures.map((c) => ({ ...c, device: "tablet" }));
  fs.writeFileSync(manifestFile, JSON.stringify(manifest));
  assert.ok(gate(tabletOnly).some((p) => p.includes("is not in")));
  const missing = rawTree();
  fs.rmSync(path.join(missing, "android", "capture-manifest.json"));
  assert.ok(gate(missing).some((p) => p.includes("missing capture manifest")));
  const noCapture = rawTree();
  fs.rmSync(path.join(noCapture, "android", "es", "phone", "02-overview.png"));
  assert.ok(gate(noCapture).some((p) => p.includes("missing capture")));
});

// --- copy ----------------------------------------------------------------------------------------

test("the shipped copy passes the store copy rules, and banned phrases are caught", () => {
  const copies = Object.fromEntries(screens.locales.map((l) => [l.id, loadCopy(l.id)]));
  assert.deepEqual(copyProblems(targetsConfig, screens, copies), []);
  const bad = structuredClone(copies);
  bad.es.screens.overview.title = "La mejor app: descargá ahora";
  bad.en.screens.overview.subtitle = "The #1 budget app";
  const problems = copyProblems(targetsConfig, screens, bad);
  assert.ok(problems.some((p) => p.includes('"mejor"')));
  assert.ok(problems.some((p) => p.includes('"#1"')));
  // Whole words only: "newsletter" or "topic" must not trip "new"/"top".
  bad.en.screens.overview.subtitle = "Topics and newsletters";
  assert.ok(!copyProblems(targetsConfig, screens, bad).some((p) => p.includes('"new"') || p.includes('"top"')));
});

test("a paid screen must carry its plan badge and a Free screen none", () => {
  const copies = Object.fromEntries(screens.locales.map((l) => [l.id, loadCopy(l.id)]));
  const bad = structuredClone(copies);
  bad.es.screens.budget.plan_badge = null; // Basic feature shown as if it were free
  bad.en.screens.mail.plan_badge = "basic"; // VIP feature under the wrong plan
  bad.en.screens.movements.plan_badge = "vip"; // Free feature labelled as paid
  const problems = copyProblems(targetsConfig, screens, bad).join("\n");
  assert.match(problems, /es\.json: budget badge is none, the screen needs basic/);
  assert.match(problems, /en\.json: mail badge is basic, the screen needs vip/);
  assert.match(problems, /en\.json: movements badge is vip, the screen needs none/);
});

// --- validator -----------------------------------------------------------------------------------

const PHONE_SCREENS = screensFor(screens, target("google-phone"), true);

/**
 * A composed final image, the raw capture its provenance points to and that capture's record in the
 * capture manifest, all consistent. Image "0N" shows the Nth Android screen, in Spanish.
 */
function writeImage(dir, tgt, locale, name, { width = tgt.width, height = tgt.height, meta = {}, alpha = false, provenance = true } = {}) {
  const folder = path.join(dir, tgt.store, locale, tgt.id);
  fs.mkdirSync(folder, { recursive: true });
  const png = alpha ? rgbaPng(width, height, [0, 0, 0, 255]) : encodeRgbPng({ width, height, pixels: Buffer.alloc(width * height * 3) });
  const platform = tgt.store === "apple" ? "ios" : "android";
  const screen = PHONE_SCREENS[(Number(name) - 1) % PHONE_SCREENS.length];
  const base = Number(name) <= PHONE_SCREENS.length ? screen.id : `${screen.id}-extra`; // files are named after their screen
  fs.writeFileSync(path.join(folder, `${base}.png`), png);
  const capture = tinyPng([Number(name), 1, 2]);
  const file = `raw/${platform}/es/phone/${screen.id}.png`;
  fs.mkdirSync(path.dirname(path.join(dir, file)), { recursive: true });
  fs.writeFileSync(path.join(dir, file), capture);
  const manifestFile = path.join(dir, "raw", platform, "capture-manifest.json");
  const manifest = fs.existsSync(manifestFile) ? JSON.parse(fs.readFileSync(manifestFile, "utf8"))
    : { platform, fixture: "STORE", source_commit: AFTER, source_dirty: false, built: true, captures: [] };
  manifest.captures = manifest.captures.filter((c) => c.id !== screen.id)
    .concat({ id: screen.id, locale: "es", plan: screen.plan, file, sha256: sha(capture) });
  fs.writeFileSync(manifestFile, JSON.stringify(manifest));
  if (!provenance) return;
  fs.writeFileSync(path.join(folder, `${base}.json`), JSON.stringify({
    output_sha256: sha(png), mode: "final", platform, language: "es", screen: screen.id, plan: screen.plan, caption_ratio: 0.15,
    capture: { file, sha256: sha(capture), placeholder: false, fixture: "STORE" },
    source_commit: AFTER, pipeline_commit: AFTER, ...meta,
  }));
}

function validator(dir, only, options = {}) {
  return imageProblems(dir, { ...targetsConfig, targets: only }, { screens, rawRoot: dir, isAncestor, changedSince: () => false, ...options });
}

test("the validator accepts a correct final set", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  for (const n of ["01", "02", "03", "04"]) writeImage(dir, target("google-phone"), "es-419", n);
  assert.deepEqual(validator(dir, [target("google-phone")]), []);
});

test("the validator rejects wrong sizes, alpha, a caption band over 20%, previews and placeholders", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  const phone = target("google-phone");
  for (const n of ["01", "02", "03", "04"]) writeImage(dir, phone, "es-419", n);
  writeImage(dir, phone, "es-419", "05", { width: 1080, height: 1920 });
  writeImage(dir, phone, "es-419", "06", { alpha: true });
  writeImage(dir, phone, "es-419", "07", { meta: { caption_ratio: 0.23 } });
  writeImage(dir, phone, "es-419", "08", { meta: { mode: "preview", capture: { placeholder: true }, source_commit: null } });
  const problems = validator(dir, [phone]).join("\n");
  assert.match(problems, /05-goals\.png: 1080x1920, expected 1440x2560/);
  assert.match(problems, /06-budget\.png: has an alpha channel/);
  assert.match(problems, /07-strategy\.png: caption band 23\.0% > 20%/);
  assert.match(problems, /08-mail\.png: is a preview image/);
  assert.match(problems, /08-mail\.png: built from a placeholder/);
  assert.equal(validator(dir, [phone], { allowPreview: true }).some((p) => p.includes("08-mail.png")), false);

  writeImage(dir, phone, "es-419", "09");
  assert.match(validator(dir, [phone]).join("\n"), /9 images, the store accepts at most 8/);
});

test("the validator rejects a final without provenance, from before #287, of an unconfirmed screen or a changed capture", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  const phone = target("google-phone");
  writeImage(dir, phone, "es-419", "01", { provenance: false });
  writeImage(dir, phone, "es-419", "02", { meta: { source_commit: BEFORE } });
  writeImage(dir, phone, "es-419", "03", { meta: { screen: "99-accounts" } });
  writeImage(dir, phone, "es-419", "04", { meta: { plan: "vip" } });
  writeImage(dir, phone, "es-419", "05");
  fs.writeFileSync(path.join(dir, "raw/android/es/phone/05-goals.png"), tinyPng([9, 9, 9]));
  writeImage(dir, phone, "es-419", "06", { meta: { capture: { placeholder: false, fixture: "STORE" } } });
  writeImage(dir, phone, "es-419", "07", { meta: { platform: "ios" } });
  writeImage(dir, phone, "es-419", "08", { meta: { pipeline_commit: null, capture: undefined } });
  const problems = validator(dir, [phone]).join("\n");
  assert.match(problems, /01-home\.png: missing provenance 01-home\.json/);
  assert.match(problems, /02-overview\.png: app commit b+ predates the native app/);
  assert.match(problems, /03-movements\.png: screen 99-accounts is not confirmed for android/);
  assert.match(problems, /04-debts\.png: captured with plan vip, the screen needs free/);
  assert.match(problems, /05-goals\.png: capture raw\/android\/es\/phone\/05-goals\.png changed after composing/);
  assert.match(problems, /06-budget\.png: no capture file and SHA-256 recorded/);
  assert.match(problems, /07-strategy\.png: provenance platform ios, expected android/);
  assert.match(problems, /08-mail\.png: no pipeline commit recorded/);
  assert.match(problems, /08-mail\.png: fixture undefined, expected STORE/);

  // iOS: a screen the app does not have is refused for an iPhone final.
  const iphone = target("apple-iphone-69");
  writeImage(dir, iphone, "es-MX", "01", { meta: { platform: "ios", screen: "99-accounts", plan: "vip" } });
  assert.match(validator(dir, [iphone]).join("\n"), /screen 99-accounts is not confirmed for ios/);
});

test("the validator checks that an image's folder and name agree with its provenance", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  const phone = target("google-phone");
  for (const n of ["01", "02", "03", "04"]) writeImage(dir, phone, "es-419", n);
  // An English image filed under the Spanish folder, and an image renamed to another screen.
  const meta = path.join(dir, "google/es-419/google-phone/01-home.json");
  fs.writeFileSync(meta, JSON.stringify({ ...JSON.parse(fs.readFileSync(meta, "utf8")), language: "en" }));
  fs.renameSync(path.join(dir, "google/es-419/google-phone/02-overview.png"), path.join(dir, "google/es-419/google-phone/05-goals.png"));
  fs.renameSync(path.join(dir, "google/es-419/google-phone/02-overview.json"), path.join(dir, "google/es-419/google-phone/05-goals.json"));
  const problems = validator(dir, [phone]).join("\n");
  assert.match(problems, /01-home\.png: provenance language en, but the folder is es-419 \(es\)/);
  assert.match(problems, /05-goals\.png: file name does not match its screen 02-overview/);
});

test("the validator re-checks the image, its capture path and the capture manifest instead of trusting the provenance", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  const phone = target("google-phone");
  for (const n of ["01", "02", "03", "04", "05", "06"]) writeImage(dir, phone, "es-419", n);
  // 01: the image was replaced after composing.
  fs.writeFileSync(path.join(dir, "google/es-419/google-phone/01-home.png"), encodeRgbPng({ width: phone.width, height: phone.height, pixels: Buffer.alloc(phone.width * phone.height * 3, 7) }));
  // 02: its provenance points at another screen's capture (with that capture's real hash).
  const other = fs.readFileSync(path.join(dir, "raw/android/es/phone/03-movements.png"));
  const meta02 = path.join(dir, "google/es-419/google-phone/02-overview.json");
  const two = JSON.parse(fs.readFileSync(meta02, "utf8"));
  fs.writeFileSync(meta02, JSON.stringify({ ...two, capture: { ...two.capture, file: "raw/android/es/phone/03-movements.png", sha256: sha(other) } }));
  // 03: a path outside raw/.
  const meta03 = path.join(dir, "google/es-419/google-phone/03-movements.json");
  const three = JSON.parse(fs.readFileSync(meta03, "utf8"));
  fs.writeFileSync(meta03, JSON.stringify({ ...three, capture: { ...three.capture, file: "raw/../google/es-419/google-phone/03-movements.png" } }));
  const problems = validator(dir, [phone]).join("\n");
  assert.match(problems, /01-home\.png: the image changed after composing/);
  assert.match(problems, /02-overview\.png: capture raw\/android\/es\/phone\/03-movements\.png is not raw\/android\/es\/phone\/02-overview\.png/);
  assert.match(problems, /02-overview\.png: its capture differs from the one in the capture manifest/);
  assert.match(problems, /03-movements\.png: capture raw\/\.\.\/google.* is not raw\/android\/es\/phone\/03-movements\.png/);

  // The capture run was dirty or --no-build: every image from it is refused.
  const manifestFile = path.join(dir, "raw/android/capture-manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestFile, "utf8"));
  fs.writeFileSync(manifestFile, JSON.stringify({ ...manifest, built: false }));
  assert.match(validator(dir, [phone]).join("\n"), /04-debts\.png: the capture run was not a clean build of its commit/);
  fs.writeFileSync(manifestFile, JSON.stringify({ ...manifest, source_commit: BRANCH }));
  assert.match(validator(dir, [phone]).join("\n"), /04-debts\.png: the capture manifest names another app commit/);
  fs.rmSync(manifestFile);
  assert.match(validator(dir, [phone]).join("\n"), /04-debts\.png: no capture manifest/);
});

test("the validator refuses finals whose copy, templates or app changed after they were made", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-out-"));
  const phone = target("google-phone");
  for (const n of ["01", "02", "03", "04"]) writeImage(dir, phone, "es-419", n);
  const copyChanged = validator(dir, [phone], { changedSince: (commit, paths) => paths.some((p) => p.endsWith("store-assets/copy")) }).join("\n");
  assert.match(copyChanged, /01-home\.png: copy, templates, config or brand changed after it was composed/);
  const appChanged = validator(dir, [phone], { changedSince: (commit, paths) => paths.includes("jarvis-personal/native") }).join("\n");
  assert.match(appChanged, /01-home\.png: the app \(jarvis-personal\/native\) changed after a+: re-capture|01\.png: the app \(jarvis-personal\/native\) changed after aaaaaaaa: re-capture/);
});
