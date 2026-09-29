#!/usr/bin/env node
// Validate composed store images and the store copy against config/targets.json.
//
//   node jarvis-personal/store-assets/scripts/validate.mjs                 # output/final (upload set)
//   node jarvis-personal/store-assets/scripts/validate.mjs --dir output/preview --allow-preview
//   node jarvis-personal/store-assets/scripts/validate.mjs --require-main  # before uploading: app commit on origin/main
//
// Checks, per store and locale: count within limits, exact pixel size, PNG without alpha,
// Google's side/ratio limits and the <= 20% caption band, banned promotional phrases in the
// copy, plan badges that match each screen's plan, and provenance. An upload set may contain
// only `final` images, each with its .json provenance, built from a real capture (no
// placeholder) whose SHA-256 still matches raw/, of a screen confirmed for that platform, from
// an app commit on main that contains the #287 native app. Exit code 1 on any problem.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pngInfo } from "./png.mjs";
import { appCommitProblems, gitIsAncestor, loadCopy, loadScreens, loadTargets, platformOf, root } from "./compose.mjs";

export function copyProblems(targetsConfig, screens, copies) {
  const problems = [];
  const banned = targetsConfig.rules.google.banned_phrases;
  for (const [lang, copy] of Object.entries(copies)) {
    const texts = [copy.brand.tagline, copy.feature_graphic.title, copy.feature_graphic.subtitle];
    for (const screen of screens.screens) {
      const text = copy.screens[screen.copy_key];
      if (!text?.title) { problems.push(`copy/${lang}.json: no title for ${screen.copy_key}`); continue; }
      texts.push(text.title, text.subtitle);
      if (text.plan_badge && !copy.plan_badges[text.plan_badge]) problems.push(`copy/${lang}.json: unknown plan badge ${text.plan_badge}`);
      const expectedBadge = screen.plan && screen.plan !== "free" ? screen.plan : null;
      if ((text.plan_badge ?? null) !== expectedBadge) problems.push(`copy/${lang}.json: ${screen.copy_key} badge is ${text.plan_badge ?? "none"}, the screen needs ${expectedBadge ?? "none"} (plan ${screen.plan})`);
      if (text.title.length > 48) problems.push(`copy/${lang}.json: ${screen.copy_key} title is ${text.title.length} chars (max 48)`);
      if (text.subtitle && text.subtitle.length > 60) problems.push(`copy/${lang}.json: ${screen.copy_key} subtitle is ${text.subtitle.length} chars (max 60)`);
    }
    for (const text of texts.filter(Boolean)) {
      const lower = text.toLowerCase();
      for (const phrase of banned) {
        const pattern = new RegExp(`(^|[^\\p{L}\\d])${phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^\\p{L}\\d])`, "u");
        if (pattern.test(lower)) problems.push(`copy/${lang}.json: banned promotional phrase "${phrase}" in "${text}"`);
      }
    }
  }
  const keys = Object.keys(copies).map((lang) => Object.keys(copies[lang].screens).sort().join(","));
  if (new Set(keys).size > 1) problems.push("copy files do not define the same screens in every language");
  return problems;
}

export function imageProblems(dir, targetsConfig, { allowPreview = false, screens = loadScreens(), rawRoot = root, isAncestor = gitIsAncestor, requireMain = false } = {}) {
  const problems = [];
  const { google } = targetsConfig.rules;
  if (!fs.existsSync(dir)) return [`no images at ${dir}`];
  for (const target of targetsConfig.targets) {
    const storeDir = path.join(dir, target.store);
    const locales = fs.existsSync(storeDir) ? fs.readdirSync(storeDir) : [];
    if (target.required && !locales.length) problems.push(`${target.id}: no locale folders under ${path.relative(root, storeDir)}`);
    for (const locale of locales) {
      const folder = path.join(storeDir, locale, target.id);
      const pngs = fs.existsSync(folder) ? fs.readdirSync(folder).filter((f) => f.endsWith(".png")).sort() : [];
      const where = `${target.id}/${locale}`;
      if (target.required && pngs.length < target.min_count) problems.push(`${where}: ${pngs.length} images, needs at least ${target.min_count}`);
      if (pngs.length > target.max_count) problems.push(`${where}: ${pngs.length} images, the store accepts at most ${target.max_count}`);
      for (const name of pngs) {
        const file = path.join(folder, name);
        const label = `${where}/${name}`;
        const info = pngInfo(fs.readFileSync(file));
        if (info.width !== target.width || info.height !== target.height) problems.push(`${label}: ${info.width}x${info.height}, expected ${target.width}x${target.height}`);
        if (info.alpha) problems.push(`${label}: has an alpha channel or transparency (rejected by the stores)`);
        if (target.store === "google" && !target.single) { // side/ratio limits are screenshot rules; the feature graphic is a fixed 1024x500
          const [short, long] = [Math.min(info.width, info.height), Math.max(info.width, info.height)];
          if (short < google.min_side || long > google.max_side) problems.push(`${label}: sides must be ${google.min_side}-${google.max_side} px`);
          if (long / short > google.max_ratio) problems.push(`${label}: long side more than ${google.max_ratio}x the short side`);
        }
        const metaFile = file.replace(/\.png$/, ".json");
        if (!fs.existsSync(metaFile)) { problems.push(`${label}: missing provenance ${path.basename(metaFile)}`); continue; }
        const meta = JSON.parse(fs.readFileSync(metaFile, "utf8"));
        if (target.store === "google" && !target.single) {
          if (typeof meta.caption_ratio !== "number") problems.push(`${label}: caption band was not measured`);
          else if (meta.caption_ratio > google.max_caption_area_ratio) problems.push(`${label}: caption band ${(meta.caption_ratio * 100).toFixed(1)}% > ${google.max_caption_area_ratio * 100}%`);
        }
        if (!allowPreview) {
          if (meta.mode !== "final") problems.push(`${label}: is a ${meta.mode} image, not a final one`);
          if (meta.capture?.placeholder) problems.push(`${label}: built from a placeholder, not a real capture`);
          if (!meta.pipeline_commit) problems.push(`${label}: no pipeline commit recorded`);
          if (!target.single) problems.push(...finalCaptureProblems(label, meta, target, screens, rawRoot, isAncestor, requireMain));
        }
      }
    }
  }
  return problems;
}

/** A final screenshot must trace back to a confirmed screen and an unchanged post-#287 capture. */
function finalCaptureProblems(label, meta, target, screens, rawRoot, isAncestor, requireMain) {
  const problems = [];
  const platform = platformOf(target);
  if (meta.platform !== platform) problems.push(`${label}: provenance platform ${meta.platform}, expected ${platform}`);
  const screen = screens.screens.find((s) => s.id === meta.screen);
  if (!screen?.platforms?.[platform]?.confirmed) problems.push(`${label}: screen ${meta.screen} is not confirmed for ${platform}`);
  else if (meta.plan !== screen.plan) problems.push(`${label}: captured with plan ${meta.plan}, the screen needs ${screen.plan}`);
  if (!meta.source_commit) problems.push(`${label}: no source commit recorded`);
  else problems.push(...appCommitProblems(meta.source_commit, screens, isAncestor, { requireMain }).map((p) => `${label}: ${p}`));
  if (!meta.capture?.file || !meta.capture?.sha256) problems.push(`${label}: no capture file and SHA-256 recorded`);
  else {
    const raw = path.join(rawRoot, meta.capture.file);
    if (!fs.existsSync(raw)) problems.push(`${label}: capture ${meta.capture.file} not found`);
    else if (crypto.createHash("sha256").update(fs.readFileSync(raw)).digest("hex") !== meta.capture.sha256) problems.push(`${label}: capture ${meta.capture.file} changed after composing`);
  }
  if (meta.capture?.fixture !== screens.fixture.scenario) problems.push(`${label}: fixture ${meta.capture?.fixture}, expected ${screens.fixture.scenario}`);
  return problems;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2);
  const dirIndex = argv.indexOf("--dir");
  const dir = path.resolve(root, dirIndex >= 0 ? argv[dirIndex + 1] : "output/final");
  const allowPreview = argv.includes("--allow-preview");
  const requireMain = argv.includes("--require-main");
  const targetsConfig = loadTargets();
  const screens = loadScreens();
  const copies = Object.fromEntries(screens.locales.map((l) => [l.id, loadCopy(l.id)]));
  const problems = [...copyProblems(targetsConfig, screens, copies), ...imageProblems(dir, targetsConfig, { allowPreview, requireMain })];
  if (problems.length) {
    console.error(`${problems.length} problem(s):\n- ${problems.join("\n- ")}`);
    process.exit(1);
  }
  console.log(`store assets valid: ${path.relative(root, dir) || "."}${allowPreview ? " (preview set: not uploadable)" : ""}`);
}
