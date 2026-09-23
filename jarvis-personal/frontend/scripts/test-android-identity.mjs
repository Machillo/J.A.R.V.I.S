import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { DINCR_APP_ID, nativeAppId } from "../src/lib/appIdentity.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const read = (path) => readFileSync(`${root}/${path}`, "utf8");

// Google Play package is permanent after the first upload: it must be the canonical id.
const gradle = read("android/app/build.gradle");
assert.match(gradle, /namespace = "com\.dincr\.app"/);
assert.match(gradle, /applicationId "com\.dincr\.app"/);
assert.ok(existsSync(`${root}/android/app/src/main/java/com/dincr/app/MainActivity.java`));
assert.ok(!existsSync(`${root}/android/app/src/main/java/com/finva`), "no legacy Java package");
assert.match(read("android/app/src/main/java/com/dincr/app/MainActivity.java"), /^package com\.dincr\.app;/m);
const strings = read("android/app/src/main/res/values/strings.xml");
assert.match(strings, /<string name="app_name">DINCR<\/string>/);
assert.match(strings, /<string name="package_name">com\.dincr\.app<\/string>/);
assert.match(strings, /<string name="custom_url_scheme">com\.dincr\.app<\/string>/);
const capacitor = JSON.parse(read("capacitor.config.json"));
assert.deepEqual([capacitor.appId, capacitor.appName], ["com.dincr.app", "DINCR"]);
assert.equal(nativeAppId, DINCR_APP_ID, "builds without VITE_NATIVE_APP_ID are the DINCR app");

// Deep links: login and mail OAuth must both reach the app.
const manifest = read("android/app/src/main/AndroidManifest.xml");
const links = [...manifest.matchAll(/<data android:scheme="([^"]+)" android:host="([^"]+)" android:pathPrefix="([^"]+)"/g)]
  .map(([, scheme, host, path]) => `${scheme}://${host}${path}`);
assert.deepEqual(links.sort(), ["com.dincr.app://auth/callback", "com.dincr.app://gmail/callback", "com.finva.app://gmail/callback"].sort());
assert.doesNotMatch(manifest, /com\.jarvis|usesCleartextTraffic="true"/);
assert.match(manifest, /android:allowBackup="false"/);
assert.equal((manifest.match(/android:exported="true"/g) || []).length, 1, "only the launcher activity is exported");
const permissions = [...manifest.matchAll(/<uses-permission android:name="([^"]+)"/g)].map(([, name]) => name).sort();
assert.deepEqual(permissions, ["android.permission.INTERNET", "android.permission.READ_EXTERNAL_STORAGE"]);

// The backend's mail OAuth return URL must be registered on both platforms.
const backend = readFileSync(new URL("../../backend/user_product/gmail_service.py", import.meta.url), "utf8");
const [, returnScheme, returnHost] = backend.match(/FINVA_GMAIL_RETURN_URL", "([a-z.]+):\/\/([a-z]+)\/callback"/);
assert.ok(links.includes(`${returnScheme}://${returnHost}/callback`), "Android receives the mail OAuth return");
assert.match(read("ios-dincr/App/App/Info.plist"), new RegExp(`<string>${returnScheme.replaceAll(".", "\\.")}</string>`), "iOS receives the mail OAuth return");

console.log("DINCR Android is com.dincr.app and receives login and mail OAuth returns.");
