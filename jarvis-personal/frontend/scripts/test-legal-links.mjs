import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const read = (path) => readFileSync(join(root, path), "utf8");
const sources = (dir) => readdirSync(join(root, dir)).flatMap((name) => {
  const path = join(dir, name);
  if (statSync(join(root, path)).isDirectory()) return sources(path);
  return /\.(jsx?|tsx?)$/.test(name) ? [path] : [];
});

// Inside the native app a same-origin legal link replaced the whole app WebView with
// a page that could not be scrolled or closed. Only the public web page may link there.
for (const file of sources("src")) {
  if (file.replaceAll("\\", "/").endsWith("pages/PublicInfoPage.jsx")) continue;
  assert.doesNotMatch(read(file), /href="\/(terms|privacy)"/, `${relative(root, join(root, file))} must open legal documents with <LegalLink>`);
}

const helper = read("src/lib/legalLinks.js");
assert.match(helper, /terms: "https:\/\/dincr\.com\/terminos\/"/, "Terms must open the official public page");
assert.match(helper, /privacy: "https:\/\/dincr\.com\/privacidad\/"/, "Privacy must open the official public page");
assert.match(helper, /Capacitor\.isNativePlatform\(\)/, "Only native builds may intercept the link");
assert.match(helper, /event\.preventDefault\(\)/, "Native builds must not navigate the app WebView");
assert.match(helper, /Browser\.open\(\{ url/, "Native builds must use the system in-app browser, which has a close button");

const link = read("src/components/LegalLink.jsx");
assert.match(link, /target="_blank" rel="noopener noreferrer"/, "On the web the document opens in a new tab");

for (const [file, count] of [["src/pages/LegalConsent.jsx", 2], ["src/users/pages/GmailAutomation.jsx", 1], ["src/users/pages/Settings.jsx", 1]]) {
  const text = read(file);
  assert.equal((text.match(/<LegalLink kind="terms"/g) || []).length, count, `${file} terms links`);
  assert.equal((text.match(/<LegalLink kind="privacy"/g) || []).length, count, `${file} privacy links`);
}

// The plugin must be compiled into both native DINCR apps.
assert.match(read("capacitor.ios.finva.json"), /"@capacitor\/browser"/, "iOS DINCR must include @capacitor/browser");
assert.match(read("android/capacitor.settings.gradle"), /capacitor-browser/, "Android must include @capacitor/browser");

console.log("DINCR legal links open the official pages in the system browser.");
