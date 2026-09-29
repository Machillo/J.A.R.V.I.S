#!/usr/bin/env node
// Compose store images from REAL captures of the DINCR app + templates + ES/EN copy.
//
//   node jarvis-personal/store-assets/scripts/compose.mjs --mode preview
//   node jarvis-personal/store-assets/scripts/compose.mjs --mode final --source-commit <sha>
//
// preview  Layout proofs. A missing capture becomes a neutral placeholder panel that says so,
//          and every image carries a "PREVIEW" watermark: never uploadable.
// final    Store images. Refuses unless the release gate in config/screens.json is open, every
//          screen used is `confirmed`, its capture exists under raw/, and the capture manifest's
//          commit is on origin/main. It never draws UI: the only UI is the real capture.
//
// Rendering: headless Chromium (Chrome or Edge, found automatically or via DINCR_BROWSER) at
// the exact target size; the PNG is then flattened to opaque RGB (stores reject alpha).
import { execFileSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { decodePng, encodeRgbPng, flattenToRgb, hexToRgb, pngInfo } from "./png.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
export const root = path.resolve(here, "..");
const repoRoot = path.resolve(root, "../..");

export const readJson = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
export const loadTargets = () => readJson(path.join(root, "config/targets.json"));
export const loadScreens = () => readJson(path.join(root, "config/screens.json"));
export const loadCopy = (lang) => readJson(path.join(root, `copy/${lang}.json`));

/** Where the capture of one screen lives: raw/<platform>/<locale>/<device>/<screen>.png */
export function rawPathFor(target, locale, screenId, rawDir = path.join(root, "raw")) {
  const platform = target.store === "apple" ? "ios" : "android";
  const device = target.id === "apple-ipad-13" ? "tablet" : "phone";
  return path.join(rawDir, platform, locale, device, `${screenId}.png`);
}

/** DESIGN.md colors via the native token parser, so the store images use the same palette. */
export async function brandColors() {
  const { parseTokens } = await import(pathToFileURL(path.join(repoRoot, "jarvis-personal/native/design-tokens/generate.mjs")).href);
  const tokens = parseTokens(fs.readFileSync(path.join(repoRoot, "DESIGN.md"), "utf8"));
  const colors = {};
  for (const { key, light, dark } of tokens.colors) {
    colors[`c_${key.replace(/-/g, "_")}`] = light;
    colors[`c_dark_${key.replace(/-/g, "_")}`] = dark;
  }
  return colors;
}

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

export function fill(template, values) {
  return template.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    if (!(key in values)) throw new Error(`template placeholder without a value: ${match}`);
    return key === "watermark" || key === "screenshot" || key === "icon" ? values[key] : escapeHtml(values[key]);
  });
}

export function findBrowser() {
  const candidates = [
    process.env.DINCR_BROWSER,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error("no Chromium browser found; set DINCR_BROWSER to Chrome/Edge/Chromium");
  return found;
}

function browserArgs(width, height, profile) {
  return [
    "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
    "--force-device-scale-factor=1", "--allow-file-access-from-files", "--disable-extensions",
    `--user-data-dir=${profile}`, `--window-size=${width},${height}`, "--virtual-time-budget=4000",
  ];
}

/** Render an HTML file to an exact-size PNG; also return the caption band ratio measured in the DOM. */
export function render(browser, htmlFile, outFile, width, height) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-store-"));
  try {
    const url = pathToFileURL(htmlFile).href;
    execFileSync(browser, [...browserArgs(width, height, profile), `--screenshot=${outFile}`, url], { stdio: "ignore", timeout: 60000 });
    const probe = `${url}#measure`;
    const dom = execFileSync(browser, [...browserArgs(width, height, profile), "--dump-dom", probe], { encoding: "utf8", timeout: 60000 });
    const ratio = Number((/data-caption-ratio="([\d.]+)"/.exec(dom) || [])[1]);
    const shotOk = /data-shot-loaded="true"/.test(dom);
    return { captionRatio: Number.isFinite(ratio) ? ratio : null, screenshotLoaded: shotOk };
  } finally {
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

// Injected into every page: measures the caption band and whether the capture image loaded.
const MEASURE = `<script>
  addEventListener("load", () => {
    // Conservative text band: from the top of the first to the bottom of the last VISIBLE caption
    // element (brand row, title, subtitle, plan badge), as a share of the image HEIGHT (full width
    // assumed), so it over-estimates Google's "tagline area" rule rather than under-estimating it.
    const parts = [...document.querySelectorAll("#caption > *")]
      .map((el) => el.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
    const shot = document.getElementById("shot");
    const band = parts.length ? Math.max(...parts.map((r) => r.bottom)) - Math.min(...parts.map((r) => r.top)) : 0;
    document.body.dataset.captionRatio = (band / innerHeight).toFixed(4);
    document.body.dataset.shotLoaded = shot ? String(shot.complete && shot.naturalWidth > 0) : "true";
  });
</script>`;

function writeOpaquePng(renderedFile, outFile, background) {
  const decoded = decodePng(fs.readFileSync(renderedFile));
  const rgb = flattenToRgb(decoded, background);
  fs.writeFileSync(outFile, encodeRgbPng(rgb));
  return pngInfo(fs.readFileSync(outFile));
}

const sha256 = (file) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");

function gitIsOnMain(commit) {
  try {
    execFileSync("git", ["-C", repoRoot, "merge-base", "--is-ancestor", commit, "origin/main"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/** Every reason the final run must not start. Empty list = allowed. */
export function finalGateProblems({ screens, targets, locales, rawDir, sourceCommit, isOnMain = gitIsOnMain }) {
  const problems = [];
  if (screens.release_gate?.status !== "released") {
    problems.push(`release gate closed: PR #${screens.release_gate?.pr} (${screens.release_gate?.reason})`);
  }
  if (!sourceCommit) problems.push("--source-commit is required (the commit of the app build that was captured)");
  else if (!isOnMain(sourceCommit)) problems.push(`source commit ${sourceCommit} is not on origin/main`);
  const usable = screens.screens.filter((screen) => screen.confirmed);
  if (!usable.length) problems.push("no screen is confirmed in config/screens.json");
  for (const target of targets.filter((t) => !t.single)) {
    for (const locale of locales) {
      const manifest = path.join(rawDir, target.store === "apple" ? "ios" : "android", "capture-manifest.json");
      if (!fs.existsSync(manifest)) problems.push(`missing capture manifest ${path.relative(root, manifest)}`);
      else if (sourceCommit && readJson(manifest).source_commit !== sourceCommit) problems.push(`${path.relative(root, manifest)} was captured from another commit`);
      for (const screen of usable) {
        const raw = rawPathFor(target, locale.id, screen.id, rawDir);
        if (!fs.existsSync(raw)) problems.push(`missing capture ${path.relative(root, raw)}`);
      }
    }
  }
  return [...new Set(problems)];
}

function placeholderHtml(width, height, colors, label) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;width:${width}px;height:${height}px;overflow:hidden}
    body{background:repeating-linear-gradient(135deg,${colors.c_dark_surface} 0 ${width / 18}px,${colors.c_dark_surface_2} ${width / 18}px ${width / 9}px);
      display:flex;align-items:center;justify-content:center;font-family:"Segoe UI",Roboto,Arial,sans-serif}
    div{max-width:80%;text-align:center;color:${colors.c_dark_text_2};font-size:${width / 16}px;font-weight:700;line-height:1.3;
      border:${width / 120}px dashed ${colors.c_dark_line_strong};padding:${width / 14}px;border-radius:${width / 20}px}
  </style></head><body><div>${escapeHtml(label)}</div></body></html>`;
}

// Placeholder capture sizes: typical native screen sizes of each device class (aspect matters).
const PLACEHOLDER_SIZE = { "apple-iphone-69": [1206, 2622], "apple-ipad-13": [2064, 2752], "google-phone": [1080, 2400] };

function parseArgs(argv) {
  const args = { mode: "preview", targets: null, locales: null, rawDir: path.join(root, "raw"), outDir: null, sourceCommit: null };
  for (let i = 0; i < argv.length; i += 1) {
    const [flag, value] = [argv[i], argv[i + 1]];
    if (flag === "--mode") args.mode = value;
    else if (flag === "--targets") args.targets = value.split(",");
    else if (flag === "--locales") args.locales = value.split(",");
    else if (flag === "--raw-dir") args.rawDir = path.resolve(value);
    else if (flag === "--out-dir") args.outDir = path.resolve(value);
    else if (flag === "--source-commit") args.sourceCommit = value;
    else continue;
    i += 1;
  }
  if (!["preview", "final"].includes(args.mode)) throw new Error("--mode must be preview or final");
  args.outDir ??= path.join(root, "output", args.mode);
  return args;
}

export async function compose(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const targetsConfig = loadTargets();
  const screens = loadScreens();
  const targets = targetsConfig.targets.filter((t) => !args.targets || args.targets.includes(t.id));
  const locales = screens.locales.filter((l) => !args.locales || args.locales.includes(l.id));
  const final = args.mode === "final";

  if (final) {
    const problems = finalGateProblems({ screens, targets, locales, rawDir: args.rawDir, sourceCommit: args.sourceCommit });
    if (problems.length) {
      console.error("REFUSED: final store images cannot be generated:\n- " + problems.join("\n- "));
      process.exitCode = 2;
      return [];
    }
  }

  const colors = await brandColors();
  const background = hexToRgb(colors.c_dark_bg);
  const browser = findBrowser();
  const icon = pathToFileURL(path.join(repoRoot, "jarvis-personal/frontend/resources/icon.png")).href;
  const screenTemplate = fs.readFileSync(path.join(root, "templates/screen.html"), "utf8");
  const featureTemplate = fs.readFileSync(path.join(root, "templates/feature-graphic.html"), "utf8");
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "dincr-store-work-"));
  const written = [];

  try {
    for (const locale of locales) {
      const copy = loadCopy(locale.id);
      for (const target of targets) {
        const storeLocale = target.store === "apple" ? locale.apple : locale.google;
        const outDir = path.join(args.outDir, target.store, storeLocale, target.id);
        fs.mkdirSync(outDir, { recursive: true });
        const watermark = final ? "" : `<span>PREVIEW · ${locale.id === "es" ? "NO PARA STORES" : "NOT FOR STORES"}</span>`;
        const common = { ...colors, width: target.width, height: target.height, lang: locale.id, brand_name: copy.brand.name, icon, watermark };

        const jobs = target.single
          ? [{ id: "feature-graphic", html: fill(featureTemplate, { ...common, ...copy.feature_graphic }), source: null }]
          : screens.screens.filter((s) => (final ? s.confirmed : true)).slice(0, target.max_count).map((screen) => {
            const text = copy.screens[screen.copy_key];
            if (!text) throw new Error(`copy/${locale.id}.json has no caption for ${screen.copy_key}`);
            let source = rawPathFor(target, locale.id, screen.id, args.rawDir);
            let placeholder = false;
            if (!fs.existsSync(source)) {
              if (final) throw new Error(`missing capture ${source}`);
              placeholder = true;
              const [w, h] = PLACEHOLDER_SIZE[target.id];
              const label = locale.id === "es" ? `Captura real de "${screen.area}" · POST-#287` : `Real capture of "${screen.area}" · POST-#287`;
              const phHtml = path.join(work, `ph-${target.id}-${locale.id}-${screen.id}.html`);
              fs.writeFileSync(phHtml, placeholderHtml(w, h, colors, label));
              source = path.join(work, `ph-${target.id}-${locale.id}-${screen.id}.png`);
              render(browser, phHtml, source, w, h);
            }
            const wide = target.width / target.height > 0.6;
            const layout = `${target.template}${wide ? " wide" : ""}`;
            const html = fill(screenTemplate, {
              ...common, layout, frame_class: target.template === "apple" ? "device" : "card",
              title: text.title, subtitle: text.subtitle,
              badge: text.plan_badge ? copy.plan_badges[text.plan_badge] : "",
              screenshot: pathToFileURL(source).href,
            });
            return { id: screen.id, html, source, placeholder };
          });

        for (const job of jobs) {
          const htmlFile = path.join(work, `${target.id}-${locale.id}-${job.id}.html`);
          fs.writeFileSync(htmlFile, job.html.replace("</body>", `${MEASURE}</body>`));
          const rendered = path.join(work, `${target.id}-${locale.id}-${job.id}.rgba.png`);
          const measured = render(browser, htmlFile, rendered, target.width, target.height);
          if (!measured.screenshotLoaded) throw new Error(`capture did not load in ${htmlFile}`);
          const outFile = path.join(outDir, `${job.id}.png`);
          const info = writeOpaquePng(rendered, outFile, background);
          if (info.width !== target.width || info.height !== target.height) {
            throw new Error(`${outFile} rendered ${info.width}x${info.height}, expected ${target.width}x${target.height}`);
          }
          const meta = {
            mode: args.mode, target: target.id, store: target.store, locale: storeLocale, screen: job.id,
            width: info.width, height: info.height, alpha: info.alpha,
            caption_ratio: target.single ? null : measured.captionRatio,
            capture: job.source ? { file: path.relative(root, job.source).replace(/\\/g, "/"), sha256: sha256(job.source), placeholder: Boolean(job.placeholder) } : null,
            source_commit: final ? args.sourceCommit : null,
          };
          fs.writeFileSync(outFile.replace(/\.png$/, ".json"), `${JSON.stringify(meta, null, 2)}\n`);
          fs.copyFileSync(htmlFile, outFile.replace(/\.png$/, ".html")); // the exact editable source of this image
          written.push(outFile);
          console.log(`${final ? "final" : "preview"} ${path.relative(root, outFile)} ${info.width}x${info.height}`);
        }
      }
    }
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
  return written;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  compose().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
