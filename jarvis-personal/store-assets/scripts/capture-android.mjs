#!/usr/bin/env node
// Capture the Android store screens from the REAL native app on an emulator, end to end:
// build + install (Debug, STORE fixture) -> clean status bar and fixed clock -> per language, the
// opt-in instrumentation test StoreScreenshots.kt navigates and saves each screen -> pull ->
// raw/android/<es|en>/phone/<id>.png + raw/android/capture-manifest.json (provenance).
//
//   node jarvis-personal/store-assets/scripts/capture-android.mjs            # build, install, capture
//   node jarvis-personal/store-assets/scripts/capture-android.mjs --no-build # use the installed build
//
// Needs: a running emulator (adb), JAVA_HOME with JDK 17 for the build. The device is restored
// afterwards (automatic time, demo mode off, app language reset). Nothing is uploaded anywhere.
import { execFileSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pngInfo } from "./png.mjs";
import { loadScreens, root } from "./compose.mjs";

const repoRoot = path.resolve(root, "../..");
const androidDir = path.join(repoRoot, "jarvis-personal/native/android");
export const PACKAGE = "com.dincr.app";
const RUNNER = `${PACKAGE}.test/androidx.test.runner.AndroidJUnitRunner`;
const TEST_CLASS = `${PACKAGE}.StoreScreenshots`;
const DEVICE_DIR = `/sdcard/Android/data/${PACKAGE}/files/store`;
/** The STORE sample's "today" (StoreSample.kt), 09:41 in Costa Rica (UTC-6), so "Hoy/Ayer" labels match the data. */
export const FIXTURE_DATE = "2026-09-28";
export const DEVICE_CLOCK_MS = Date.UTC(2026, 8, 28, 15, 41, 0);
export const TIME_ZONE = "America/Costa_Rica";

/** Status bar for store images: 09:41, full battery and Wi-Fi, no mobile data type, no notifications. */
export const DEMO_MODE = [
  ["enter"],
  ["clock", "-e", "hhmm", "0941"],
  ["battery", "-e", "level", "100", "-e", "plugged", "false"],
  ["network", "-e", "wifi", "show", "-e", "level", "4", "-e", "fully", "true"],
  ["network", "-e", "mobile", "hide"],
  ["notifications", "-e", "visible", "false"],
];

/** `am instrument` prints "OK (n tests)" only when every test passed and none was skipped by the opt-in. */
export function instrumentPassed(output, expected) {
  const ok = /OK \((\d+) tests?\)/.exec(output);
  return Boolean(ok) && Number(ok[1]) === expected && !/FAILURES!!!|Process crashed|INSTRUMENTATION_FAILED/.test(output);
}

const sha256 = (buffer) => crypto.createHash("sha256").update(buffer).digest("hex");
const git = (...args) => execFileSync("git", ["-C", repoRoot, ...args], { encoding: "utf8" }).trim();

function adbPath() {
  const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || (process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "Android/Sdk"));
  const exe = sdk && path.join(sdk, "platform-tools", process.platform === "win32" ? "adb.exe" : "adb");
  return exe && fs.existsSync(exe) ? exe : "adb";
}

export async function captureAndroid(argv = process.argv.slice(2)) {
  const build = !argv.includes("--no-build");
  const adb = adbPath();
  const run = (...args) => execFileSync(adb, args, { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }).trim();
  const shell = (...args) => run("shell", ...args);
  const screens = loadScreens();
  const android = screens.screens.filter((s) => s.platforms?.android?.available);
  if (!android.length) throw new Error("config/screens.json lists no Android screen");

  // Provenance: the capture must come from a committed tree, or the manifest says it did not.
  const commit = git("rev-parse", "HEAD");
  const dirty = git("status", "--porcelain", "--", "jarvis-personal/native", "jarvis-personal/store-assets/config").length > 0;

  if (build) {
    const gradle = path.join(androidDir, process.platform === "win32" ? "gradlew.bat" : "gradlew");
    execFileSync(gradle, ["installDincrDebug", "installDincrDebugAndroidTest", "-q", "--console=plain"], { cwd: androidDir, stdio: "inherit", shell: process.platform === "win32" });
  }

  const devices = run("devices").split("\n").slice(1).filter((l) => /\tdevice$/.test(l));
  if (devices.length !== 1) throw new Error(`expected exactly one adb device, found ${devices.length}`);
  const [width, height] = (/(\d+)x(\d+)/.exec(shell("wm", "size")) || []).slice(1).map(Number);
  const device = {
    model: shell("getprop", "ro.product.model"), sdk: Number(shell("getprop", "ro.build.version.sdk")),
    width, height, density: Number((/(\d+)/.exec(shell("wm", "density")) || [])[1]),
  };
  const packageInfo = shell("dumpsys", "package", PACKAGE);
  const app = {
    package: PACKAGE, flavor: "dincr", build_type: "debug",
    version_name: (/versionName=(\S+)/.exec(packageInfo) || [])[1] ?? null,
    last_update: (/lastUpdateTime=([^\n]+)/.exec(packageInfo) || [])[1]?.trim() ?? null,
  };

  const saved = { autoTime: shell("settings", "get", "global", "auto_time"), timeZone: shell("getprop", "persist.sys.timezone") };
  const pulled = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-android-"));
  const records = [];
  try {
    shell("settings", "put", "global", "auto_time", "0");
    shell("cmd", "alarm", "set-timezone", TIME_ZONE);
    shell("cmd", "alarm", "set-time", String(DEVICE_CLOCK_MS));
    shell("settings", "put", "global", "sysui_demo_allowed", "1");
    for (const command of DEMO_MODE) shell("am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", ...command);

    for (const locale of screens.locales) {
      shell("cmd", "locale", "set-app-locales", PACKAGE, "--locales", locale.android_locale);
      shell("rm", "-rf", DEVICE_DIR);
      const output = run("shell", "am", "instrument", "-w", "-e", "storeScreenshots", "true", "-e", "class", TEST_CLASS, RUNNER);
      if (!instrumentPassed(output, android.length)) throw new Error(`capture run failed for ${locale.id}:\n${output}`);
      run("pull", `${DEVICE_DIR}/${locale.id}`, path.join(pulled, locale.id));
      for (const screen of android) {
        const source = path.join(pulled, locale.id, `${screen.id}.png`);
        if (!fs.existsSync(source)) throw new Error(`the run did not produce ${locale.id}/${screen.id}.png`);
        const buffer = fs.readFileSync(source);
        const info = pngInfo(buffer);
        if (info.width !== width || info.height !== height) throw new Error(`${locale.id}/${screen.id}.png is ${info.width}x${info.height}, the screen is ${width}x${height}`);
        const target = path.join(root, "raw/android", locale.id, "phone", `${screen.id}.png`);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, buffer);
        records.push({ id: screen.id, locale: locale.id, plan: screen.platforms.android.plan, file: path.relative(root, target).replace(/\\/g, "/"), sha256: sha256(buffer), width: info.width, height: info.height });
      }
    }
  } finally {
    const quiet = (...args) => { try { shell(...args); } catch { /* keep restoring */ } };
    quiet("am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "exit");
    quiet("cmd", "locale", "set-app-locales", PACKAGE, "--locales", "''"); // back to the device language
    if (saved.timeZone) quiet("cmd", "alarm", "set-timezone", saved.timeZone);
    quiet("settings", "put", "global", "auto_time", saved.autoTime === "0" ? "0" : "1");
    fs.rmSync(pulled, { recursive: true, force: true });
  }

  const manifest = {
    platform: "android", fixture: "STORE", fixture_date: FIXTURE_DATE,
    source_commit: commit, source_dirty: dirty, pipeline_commit: commit,
    captured_at: new Date().toISOString(), app, device,
    status_bar: "demo mode: 09:41, battery 100%, Wi-Fi full, no notifications",
    method: `am instrument ${TEST_CLASS} (storeScreenshots=true)`,
    captures: records,
  };
  fs.writeFileSync(path.join(root, "raw/android/capture-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`captured ${records.length} Android screens from ${commit.slice(0, 8)}${dirty ? " (DIRTY TREE: not usable for finals)" : ""}`);
  return manifest;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  captureAndroid().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
