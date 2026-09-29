#!/usr/bin/env node
// Compose store images from REAL captures of the DINCR app + templates + ES/EN copy.
//
//   node jarvis-personal/store-assets/scripts/compose.mjs --mode preview
//   node jarvis-personal/store-assets/scripts/compose.mjs --mode final --source-commit <sha>
//
// preview  Layout proofs. A missing capture becomes a neutral placeholder panel that says so,
//          and every image carries a "PREVIEW" watermark: never uploadable.
// final    Store images. Refuses unless --source-commit contains the #287 merge
//          (config/screens.json app_baseline: older builds show the Capacitor UI) and is in the
//          checked-out history (on origin/main too with --require-main), every
//          screen used is `confirmed` for that platform, and each capture exists under raw/ with
//          the SHA-256 the capture manifest recorded for a clean tree of that commit and the
//          STORE fixture. It never draws UI: the only UI is the real capture.
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

export const platformOf = (target) => (target.store === "apple" ? "ios" : "android");

/**
 * The screens a target shows, in store order. Final: only screens confirmed on that platform.
 * Preview: every screen the platform has (a missing capture becomes a labelled placeholder).
 */
export function screensFor(screens, target, final) {
  const platform = platformOf(target);
  return screens.screens.filter((s) => (final ? s.platforms?.[platform]?.confirmed === true : s.platforms?.[platform]?.available === true));
}

export const deviceOf = (target) => (target.id === "apple-ipad-13" ? "tablet" : "phone");

/** Where the capture of one screen lives: raw/<platform>/<locale>/<device>/<screen>.png */
export function rawPathFor(target, locale, screenId, rawDir = path.join(root, "raw")) {
  const platform = platformOf(target);
  const device = deviceOf(target);
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

/** Rewrites file:// links into the repository as paths relative to the saved HTML, so no local path is committed. */
export function portableHtml(html, outFile, base = repoRoot) {
  const prefix = pathToFileURL(base).href.replace(/\/?$/, "/");
  const relative = `${path.relative(path.dirname(outFile), base).split(path.sep).join("/")}/`;
  return html.split(prefix).join(relative);
}

function differingBytes(a, b) {
  if (a.length !== b.length) return "size";
  let count = 0;
  for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) count += 1;
  return String(count);
}

/**
 * Headless Chromium occasionally paints a frame with an unpainted tile (a white block at an edge).
 * Render until two consecutive renders are pixel-identical, so a glitch never reaches the output.
 */
export function renderStable(browser, htmlFile, outFile, width, height, attempts = 6, draw = render) {
  let previous = null;
  const diffs = [];
  for (let i = 0; i < attempts; i += 1) {
    const measured = draw(browser, htmlFile, outFile, width, height);
    const pixels = decodePng(fs.readFileSync(outFile)).pixels;
    if (previous && Buffer.compare(previous, pixels) === 0) return measured;
    if (previous) diffs.push(differingBytes(previous, pixels));
    previous = Buffer.from(pixels);
  }
  throw new Error(`${htmlFile} did not render the same way twice in ${attempts} attempts (differing bytes: ${diffs.join(", ")})`);
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

/** git merge-base --is-ancestor: true when `ancestor` is contained in `descendant`. */
export function gitIsAncestor(ancestor, descendant) {
  try {
    execFileSync("git", ["-C", repoRoot, "merge-base", "--is-ancestor", ancestor, descendant], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/** Paths whose change makes a capture stale (the app) or a composed image stale (its inputs). */
export const APP_PATHS = ["jarvis-personal/native"];
export const COMPOSE_INPUTS = ["jarvis-personal/store-assets/copy", "jarvis-personal/store-assets/templates",
  "jarvis-personal/store-assets/config", "DESIGN.md", "jarvis-personal/frontend/resources/icon.png"];

/** True when `paths` differ between `commit` and the working tree (committed or not). */
export function gitChangedSince(commit, paths) {
  try {
    execFileSync("git", ["-C", repoRoot, "diff", "--quiet", commit, "--", ...paths], { stdio: "ignore" });
    return false;
  } catch {
    return true;
  }
}

/**
 * Why an app commit cannot back a final image (empty = it can): built after #287, part of the
 * reviewed history, and the app unchanged since (else the capture is stale). `requireMain` (the
 * pre-upload check, once the capture PR is merged) also requires it on origin/main.
 */
export function appCommitProblems(commit, screens, isAncestor = gitIsAncestor, { requireMain = false, changedSince = gitChangedSince } = {}) {
  if (!commit) return ["no app commit recorded"];
  const problems = [];
  if (changedSince(commit, APP_PATHS)) problems.push(`the app (${APP_PATHS.join(", ")}) changed after ${commit.slice(0, 8)}: re-capture`);
  if (!isAncestor(commit, "HEAD")) problems.push(`app commit ${commit} is not in the checked-out history`);
  if (requireMain && !isAncestor(commit, "origin/main")) problems.push(`app commit ${commit} is not on origin/main`);
  const baseline = screens.app_baseline?.merge_commit;
  if (!baseline) problems.push("config/screens.json has no app_baseline.merge_commit");
  else if (!isAncestor(baseline, commit)) problems.push(`app commit ${commit} predates the native app (PR #${screens.app_baseline.pr}, ${baseline.slice(0, 8)}): it shows the Capacitor UI`);
  return problems;
}

export const rel = (file) => path.relative(root, file).split(path.sep).join("/");

/** Every reason the final run must not start. Empty list = allowed. */
export function finalGateProblems({ screens, targets, locales, rawDir, sourceCommit, isAncestor = gitIsAncestor, requireMain = false, changedSince = gitChangedSince }) {
  const problems = [];
  if (!sourceCommit) problems.push("--source-commit is required (the commit of the app build that was captured)");
  else problems.push(...appCommitProblems(sourceCommit, screens, isAncestor, { requireMain, changedSince }));
  for (const target of targets.filter((t) => !t.single)) {
    const platform = platformOf(target);
    const usable = screensFor(screens, target, true);
    if (!usable.length) { problems.push(`${target.id}: no screen is confirmed for ${platform} in config/screens.json`); continue; }
    const manifestFile = path.join(rawDir, platform, "capture-manifest.json");
    if (!fs.existsSync(manifestFile)) { problems.push(`missing capture manifest ${rel(manifestFile)}`); continue; }
    const manifest = readJson(manifestFile);
    if (sourceCommit && manifest.source_commit !== sourceCommit) problems.push(`${rel(manifestFile)} was captured from another commit`);
    if (manifest.source_dirty !== false) problems.push(`${rel(manifestFile)}: captured from a tree with uncommitted changes (or not recorded)`);
    if (manifest.fixture !== screens.fixture.scenario) problems.push(`${rel(manifestFile)}: fixture ${manifest.fixture}, expected ${screens.fixture.scenario}`);
    if (manifest.built !== true) problems.push(`${rel(manifestFile)}: the capture run did not build the app from the recorded commit (--no-build)`);
    for (const locale of locales) {
      for (const screen of usable) {
        const raw = rawPathFor(target, locale.id, screen.id, rawDir);
        if (!fs.existsSync(raw)) { problems.push(`missing capture ${rel(raw)}`); continue; }
        const record = (manifest.captures ?? []).find((c) => c.id === screen.id && c.locale === locale.id && (c.device ?? "phone") === deviceOf(target));
        if (!record) problems.push(`${rel(raw)} is not in ${rel(manifestFile)}`);
        else if (record.sha256 !== sha256(raw)) problems.push(`${rel(raw)} changed after capture (SHA-256 differs from the manifest)`);
        else if (record.plan !== screen.plan) problems.push(`${rel(raw)} was captured with plan ${record.plan}, the screen needs ${screen.plan}`);
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
  const args = { mode: "preview", targets: null, locales: null, rawDir: path.join(root, "raw"), outDir: null, sourceCommit: null, requireMain: argv.includes("--require-main") };
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
  let pipelineCommit = null;
  try { pipelineCommit = execFileSync("git", ["-C", repoRoot, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(); } catch { /* not a checkout */ }
  const locales = screens.locales.filter((l) => !args.locales || args.locales.includes(l.id));
  const final = args.mode === "final";

  if (final) {
    const problems = finalGateProblems({ screens, targets, locales, rawDir: args.rawDir, sourceCommit: args.sourceCommit, requireMain: args.requireMain });
    const rawInside = path.relative(root, args.rawDir);
    if (!rawInside || rawInside.startsWith("..") || path.isAbsolute(rawInside)) problems.push("--raw-dir must be a folder inside store-assets/ (provenance paths are relative to it)");
    if (!pipelineCommit) problems.push("not a git checkout: the pipeline commit cannot be recorded");
    else if (gitChangedSince(pipelineCommit, COMPOSE_INPUTS)) problems.push(`uncommitted changes in ${COMPOSE_INPUTS.join(", ")}: commit them first so the provenance names the inputs`);
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
          : screensFor(screens, target, final).slice(0, target.max_count).map((screen) => {
            const text = copy.screens[screen.copy_key];
            if (!text) throw new Error(`copy/${locale.id}.json has no caption for ${screen.copy_key}`);
            let source = rawPathFor(target, locale.id, screen.id, args.rawDir);
            let placeholder = false;
            if (!fs.existsSync(source)) {
              if (final) throw new Error(`missing capture ${source}`);
              placeholder = true;
              const [w, h] = PLACEHOLDER_SIZE[target.id];
              const label = locale.id === "es" ? `Falta la captura real de "${screen.area}"` : `Missing the real capture of "${screen.area}"`;
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
              // The badge follows the screen's plan (config/screens.json); validate.mjs checks the copy agrees.
              badge: screen.plan && screen.plan !== "free" ? copy.plan_badges[screen.plan] : "",
              screenshot: pathToFileURL(source).href,
            });
            return { id: screen.id, plan: screen.plan, html, source, placeholder };
          });

        for (const job of jobs) {
          const htmlFile = path.join(work, `${target.id}-${locale.id}-${job.id}.html`);
          fs.writeFileSync(htmlFile, job.html.replace("</body>", `${MEASURE}</body>`));
          const rendered = path.join(work, `${target.id}-${locale.id}-${job.id}.rgba.png`);
          const measured = renderStable(browser, htmlFile, rendered, target.width, target.height);
          if (!measured.screenshotLoaded) throw new Error(`capture did not load in ${htmlFile}`);
          const outFile = path.join(outDir, `${job.id}.png`);
          const info = writeOpaquePng(rendered, outFile, background);
          if (info.width !== target.width || info.height !== target.height) {
            throw new Error(`${outFile} rendered ${info.width}x${info.height}, expected ${target.width}x${target.height}`);
          }
          const manifestFile = path.join(args.rawDir, platformOf(target), "capture-manifest.json");
          const manifest = !target.single && !job.placeholder && fs.existsSync(manifestFile) ? readJson(manifestFile) : null;
          const meta = {
            output_sha256: sha256(outFile),
            mode: args.mode, target: target.id, store: target.store, platform: target.single ? null : platformOf(target),
            locale: storeLocale, language: locale.id, screen: job.id, plan: job.plan ?? null,
            width: info.width, height: info.height, alpha: info.alpha,
            caption_ratio: target.single ? null : measured.captionRatio,
            capture: job.source ? {
              file: job.placeholder ? null : rel(job.source), sha256: sha256(job.source), placeholder: Boolean(job.placeholder),
              fixture: manifest?.fixture ?? null, fixture_date: manifest?.fixture_date ?? null,
              captured_at: manifest?.captured_at ?? null, device: manifest?.device ?? null,
            } : null,
            source_commit: final ? args.sourceCommit : null,
            app_baseline: final ? screens.app_baseline.merge_commit : null,
            pipeline_commit: pipelineCommit,
            generated_at: new Date().toISOString(),
          };
          fs.writeFileSync(outFile.replace(/\.png$/, ".json"), `${JSON.stringify(meta, null, 2)}\n`);
          // The exact editable source of this image, with repo-relative links (no local paths).
          fs.writeFileSync(outFile.replace(/\.png$/, ".html"), portableHtml(fs.readFileSync(htmlFile, "utf8"), outFile));
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
