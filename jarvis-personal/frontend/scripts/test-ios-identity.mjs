import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { DINCR_APP_ID, isDincrAppId, isMailOAuthCallback } from "../src/lib/appIdentity.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const read = (path) => readFileSync(`${root}/${path}`, "utf8");
const IOS = "ios-dincr";

// One public iOS app: DINCR. No separate FINVA or JARVIS/Owner project may return.
assert.equal(DINCR_APP_ID, "com.dincr.app");
assert.ok(existsSync(`${root}/${IOS}/App/App.xcodeproj/project.pbxproj`), "the canonical iOS project is ios-dincr");
const iosProjects = readdirSync(root).filter((name) => /^ios-/.test(name));
assert.deepEqual(iosProjects, [IOS], "only one iOS project may exist");
const iosConfigs = readdirSync(root).filter((name) => /^capacitor\.ios\..*\.json$/.test(name));
assert.deepEqual(iosConfigs, ["capacitor.ios.dincr.json"], "only the DINCR iOS Capacitor config may exist");

const project = read(`${IOS}/App/App.xcodeproj/project.pbxproj`);
const bundleIds = [...project.matchAll(/PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);/g)].map((match) => match[1]);
assert.ok(bundleIds.length >= 2, "Debug and Release define the bundle id");
assert.deepEqual([...new Set(bundleIds)], ["com.dincr.app"], "every iOS build configuration is com.dincr.app");
assert.doesNotMatch(project, /com\.finva\.app|com\.jarvis\./, "no legacy bundle id in the Xcode project");
assert.doesNotMatch(project, /DEVELOPMENT_TEAM|PROVISIONING_PROFILE_SPECIFIER = "?[^";]/, "signing identity stays local to each Mac");

const plist = read(`${IOS}/App/App/Info.plist`);
assert.match(plist, /<key>CFBundleDisplayName<\/key>\s*<string>DINCR<\/string>/, "home screen name is DINCR");
assert.match(plist, /<key>NSFaceIDUsageDescription<\/key>\s*<string>DINCR [^<]+<\/string>/, "Face ID purpose is declared");
const schemes = [...plist.matchAll(/<key>CFBundleURLSchemes<\/key>\s*<array>\s*<string>([^<]+)<\/string>/g)].map((match) => match[1]);
assert.equal(schemes[0], "com.dincr.app", "the primary URL scheme is the DINCR app id");
assert.deepEqual(schemes.slice(1), ["com.finva.app"], "only the transitional mail OAuth scheme may remain");
assert.doesNotMatch(plist, /com\.jarvis|DINCR Owner|FINVA|JARVIS/, "no legacy product identity in Info.plist");

const capacitor = JSON.parse(read("capacitor.ios.dincr.json"));
assert.equal(capacitor.appId, "com.dincr.app");
assert.equal(capacitor.appName, "DINCR");
assert.equal(capacitor.ios.path, IOS);
for (const plugin of ["@capacitor/app", "@capacitor/browser", "@aparajita/capacitor-biometric-auth", "@capacitor/filesystem", "@capacitor/share"]) {
  assert.ok(capacitor.includePlugins.includes(plugin), `iOS DINCR bundles ${plugin}`);
}
const swiftPackage = read(`${IOS}/App/CapApp-SPM/Package.swift`);
for (const product of ["CapacitorBrowser", "AparajitaCapacitorBiometricAuth", "CapacitorFilesystem", "CapacitorShare"]) {
  assert.match(swiftPackage, new RegExp(`\\.product\\(name: "${product}"`), `Swift package links ${product}`);
}

const workflow = read("scripts/ios-product.mjs");
assert.match(workflow, /config: "capacitor\.ios\.dincr\.json", appId: "com\.dincr\.app", nativePath: "ios-dincr"/);
assert.doesNotMatch(workflow, /finva:\s*\{|jarvis:\s*\{|com\.jarvis\./, "the iOS workflow builds only DINCR");
const scripts = Object.keys(JSON.parse(read("package.json")).scripts).filter((name) => name.startsWith("ios:"));
assert.deepEqual(scripts.sort(), ["ios:open", "ios:sync"]);

const ignore = read(`${IOS}/.gitignore`);
for (const pattern of ["xcuserdata", "DerivedData", "App/App/public", "*.mobileprovision", "*.p12"]) {
  assert.ok(ignore.includes(pattern), `${IOS}/.gitignore excludes ${pattern}`);
}

// OAuth returns: login uses the build's own scheme; mail OAuth accepts both DINCR schemes.
assert.ok(isDincrAppId("com.dincr.app") && isDincrAppId("com.finva.app"));
assert.equal(isDincrAppId("com.jarvis.personal"), false);
assert.ok(isMailOAuthCallback("com.dincr.app://gmail/callback?microsoft=connected"));
assert.ok(isMailOAuthCallback("com.finva.app://gmail/callback?gmail=connected"));
assert.equal(isMailOAuthCallback("com.jarvis.personal://gmail/callback"), false);
assert.equal(isMailOAuthCallback("https://evil.example/com.dincr.app://gmail/callback"), false);
assert.match(read("src/lib/nativeAuth.js"), /import \{ nativeAppId \} from "\.\/appIdentity"/, "login callback follows the build's app id");

console.log("DINCR is the only iOS app (com.dincr.app).");
