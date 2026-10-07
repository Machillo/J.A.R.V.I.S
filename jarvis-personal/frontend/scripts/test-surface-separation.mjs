import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";

// UX-10/11 — three separate surfaces (README.md): the commercial app is native iOS/Android; this web
// build on Vercel is the internal lab (never presented or indexed as the product); dincr.com is the
// static landing. Run after `npm run build:landing` (it reads landing-dist/).
const root = new URL("../", import.meta.url);
const read = (path) => readFile(new URL(path, root), "utf8");

// The lab deploy (Vercel) is never indexed, on every route.
const vercel = JSON.parse(await read("vercel.json"));
const headers = (vercel.headers ?? []).find((entry) => entry.source === "/(.*)")?.headers ?? [];
assert.ok(headers.some((h) => h.key === "X-Robots-Tag" && /noindex/.test(h.value)), "vercel.json must send X-Robots-Tag: noindex on every route");
assert.ok((vercel.rewrites ?? []).some((r) => r.destination === "/index.html"), "the lab keeps its single-page rewrite");

// The lab's page and install name say what it is.
const index = await read("index.html");
assert.match(index, /<meta name="robots" content="noindex, nofollow" \/>/, "index.html must carry the robots noindex meta");
const manifest = JSON.parse(await read("public/manifest.webmanifest"));
assert.match(manifest.name, /Lab/, "the lab's install name says it is the lab");
assert.match(manifest.short_name, /Lab/);

// The landing deploy serves only the static landing, never the lab build.
const wrangler = await read("wrangler.jsonc");
assert.match(wrangler, /"directory":\s*"\.\/landing-dist"/, "the Cloudflare Worker serves only landing-dist/");
assert.doesNotMatch(wrangler, /"directory":\s*"\.\/dist"/);

// Lab origins: the Vercel deploys (the backend lists the lab's origin for CORS).
const LAB = [/[a-z0-9-]+\.vercel\.app/i];
async function* files(dir, extensions) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if ([".build", "build", ".gradle", "node_modules", "DerivedData"].includes(entry.name)) continue;
    const url = new URL(`${entry.name}${entry.isDirectory() ? "/" : ""}`, dir);
    if (entry.isDirectory()) yield* files(url, extensions);
    else if (extensions.some((ext) => entry.name.endsWith(ext))) yield url;
  }
}
async function assertNoLabLink(dir, extensions, surface) {
  let scanned = 0;
  for await (const file of files(dir, extensions)) {
    scanned += 1;
    const text = await readFile(file, "utf8");
    for (const pattern of LAB) assert.doesNotMatch(text, pattern, `${surface} links to the internal lab: ${file.pathname}`);
  }
  assert.ok(scanned > 0, `${surface}: nothing scanned in ${dir.pathname}`);
}

// The public landing never sends users to the lab (built output, as deployed).
const landing = new URL("landing-dist/", root);
await stat(landing).catch(() => assert.fail("landing-dist/ is missing: run `npm run build:landing` first"));
await assertNoLabLink(landing, [".html", ".js", ".css", ".xml", ".txt", ".json", ".webmanifest"], "The landing");
// Store links, when configured, go to the stores (never to a web app).
const config = JSON.parse(await read("landing/config.json"));
if (config.appStoreUrl) assert.match(config.appStoreUrl, /^https:\/\/apps\.apple\.com\//);
if (config.googlePlayUrl) assert.match(config.googlePlayUrl, /^https:\/\/play\.google\.com\//);

// The commercial apps never send users to the lab either.
const native = new URL("../native/", root);
await assertNoLabLink(new URL("ios/", native), [".swift", ".plist", ".strings", ".json"], "The iOS app");
await assertNoLabLink(new URL("android/", native), [".kt", ".xml", ".json", ".properties"], "The Android app");

console.log("Surfaces stay apart: native apps are the product, the Vercel lab is internal and unindexed, the landing links neither to it.");
