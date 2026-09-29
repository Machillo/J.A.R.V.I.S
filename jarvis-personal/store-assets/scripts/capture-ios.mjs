#!/usr/bin/env node
// MAC REQUIRED. Capture the App Store screens from the REAL native iOS app on simulators, end to
// end: boot -> clean status bar -> the opt-in XCUITest DINCRUITests/StoreScreenshots.swift
// navigates and saves each screen (es and en) -> size check -> raw/ios/capture-manifest.json.
//
//   node jarvis-personal/store-assets/scripts/capture-ios.mjs
//   node jarvis-personal/store-assets/scripts/capture-ios.mjs --phone "iPhone 17 Pro Max" --tablet "iPad Pro 13-inch (M4)"
//   node jarvis-personal/store-assets/scripts/capture-ios.mjs --no-tablet   # only if the app is iPhone-only (Kenneth's decision)
//
// Needs Xcode with an iOS 17+ simulator runtime. Nothing is signed, uploaded or published.
import { execFileSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pngInfo } from "./png.mjs";
import { loadScreens, loadTargets, root } from "./compose.mjs";

const repoRoot = path.resolve(root, "../..");
const iosDir = path.join(repoRoot, "jarvis-personal/native/ios");
/** Simulator screen sizes that match the App Store targets exactly (config/targets.json). */
export const DEVICES = {
  phone: { target: "apple-iphone-69", defaultName: "iPhone 17 Pro Max" },
  tablet: { target: "apple-ipad-13", defaultName: "iPad Pro 13-inch (M4)" },
};
export const STATUS_BAR = ["--time", "9:41", "--dataNetwork", "wifi", "--wifiMode", "active", "--wifiBars", "3",
  "--cellularMode", "active", "--cellularBars", "4", "--batteryState", "charged", "--batteryLevel", "100"];

const sha256 = (buffer) => crypto.createHash("sha256").update(buffer).digest("hex");
const git = (...args) => execFileSync("git", ["-C", repoRoot, ...args], { encoding: "utf8" }).trim();
const arg = (argv, flag) => (argv.includes(flag) ? argv[argv.indexOf(flag) + 1] : null);

export async function captureIos(argv = process.argv.slice(2)) {
  if (process.platform !== "darwin") throw new Error("MAC REQUIRED: iOS captures need Xcode and the iOS Simulator");
  const screens = loadScreens();
  const targets = loadTargets().targets;
  const ios = screens.screens.filter((s) => s.platforms?.ios?.confirmed);
  const commit = git("rev-parse", "HEAD");
  const dirty = git("status", "--porcelain", "--", "jarvis-personal/native", "jarvis-personal/store-assets/config").length > 0;
  const devices = Object.entries(DEVICES).filter(([kind]) => !(kind === "tablet" && argv.includes("--no-tablet")));
  const out = path.join(root, "raw/ios");
  const records = [];
  const simulators = [];

  for (const [kind, device] of devices) {
    const name = arg(argv, `--${kind}`) ?? device.defaultName;
    const target = targets.find((t) => t.id === device.target);
    execFileSync("xcrun", ["simctl", "boot", name], { stdio: "ignore" }); // fails if the simulator does not exist
    try {
      execFileSync("xcrun", ["simctl", "status_bar", name, "override", ...STATUS_BAR], { stdio: "inherit" });
      fs.rmSync(path.join(out, "es", kind), { recursive: true, force: true });
      fs.rmSync(path.join(out, "en", kind), { recursive: true, force: true });
      execFileSync("xcodebuild", ["test", "-project", "DINCR.xcodeproj", "-scheme", "DINCR", "-destination", `platform=iOS Simulator,name=${name}`,
        "-only-testing:DINCRUITests/StoreScreenshots", "CODE_SIGNING_ALLOWED=NO"], {
        cwd: iosDir, stdio: "inherit",
        env: { ...process.env, TEST_RUNNER_DINCR_STORE_SHOTS_DIR: out, TEST_RUNNER_DINCR_STORE_DEVICE: kind },
      });
      simulators.push({ kind, name, runtime: execFileSync("xcrun", ["simctl", "list", "devices", "booted"], { encoding: "utf8" }).split("\n").find((l) => l.includes(name))?.trim() ?? null });
    } finally {
      try { execFileSync("xcrun", ["simctl", "status_bar", name, "clear"], { stdio: "ignore" }); } catch { /* keep going */ }
      try { execFileSync("xcrun", ["simctl", "shutdown", name], { stdio: "ignore" }); } catch { /* keep going */ }
    }
    for (const locale of screens.locales) {
      for (const screen of ios) {
        const file = path.join(out, locale.id, kind, `${screen.id}.png`);
        if (!fs.existsSync(file)) throw new Error(`the run did not produce ${path.relative(root, file)}`);
        const buffer = fs.readFileSync(file);
        const info = pngInfo(buffer);
        // Store images keep the capture's aspect; the capture itself must be the target's native size.
        if (info.width !== target.width || info.height !== target.height) {
          throw new Error(`${path.relative(root, file)} is ${info.width}x${info.height}; ${name} must capture ${target.width}x${target.height} (pick the right simulator)`);
        }
        records.push({ id: screen.id, locale: locale.id, device: kind, plan: screen.plan, file: path.relative(root, file).split(path.sep).join("/"), sha256: sha256(buffer), width: info.width, height: info.height });
      }
    }
  }

  const manifest = {
    platform: "ios", fixture: screens.fixture.scenario, fixture_date: screens.fixture.fixture_date,
    source_commit: commit, source_dirty: dirty, pipeline_commit: commit,
    captured_at: new Date().toISOString(),
    app: { bundle_id: "com.dincr.app.nativedev", configuration: "Debug" },
    xcode: execFileSync("xcodebuild", ["-version"], { encoding: "utf8" }).trim().split("\n")[0],
    simulators, status_bar: "simctl override: 9:41, Wi-Fi, full signal and battery",
    method: "xcodebuild test -only-testing:DINCRUITests/StoreScreenshots",
    captures: records,
  };
  fs.writeFileSync(path.join(out, "capture-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`captured ${records.length} iOS screens from ${commit.slice(0, 8)}${dirty ? " (DIRTY TREE: not usable for finals)" : ""}`);
  return manifest;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  captureIos().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
