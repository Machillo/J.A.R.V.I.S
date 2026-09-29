# DINCR store assets (App Store / Google Play)

This pipeline composes store screenshots from **real captures of the DINCR app running on synthetic
data**, with DINCR branding and ES/EN captions, at the exact sizes each store requires. It also
validates them before anyone uploads them.

> **Status: final images are BLOCKED POST-#287.** The app to publish is the native DINCR app in PR
> #287 (not merged when this was written). Final images must show that UI, so they are not produced
> from the older Capacitor UI. Everything else is ready: requirements, targets, templates, copy,
> composer, validator and tests. `--mode final` refuses to run until the gate in
> `config/screens.json` is opened. Nothing is ever uploaded by these scripts.

## Layout

| Path | What it is |
|---|---|
| `REQUIREMENTS.md` | Audit of the current Apple and Google rules (with sources and date) and the decisions derived from them |
| `CAPTURE.md` | How to capture the raw screens from the native app after #287 (iOS simulator, Android emulator), and the data rules |
| `config/targets.json` | Output sizes, counts and store rules (banned phrases, caption ≤ 20%, no alpha) |
| `config/screens.json` | Candidate screens in store order, the #287 release gate, the fixture hooks and the locales |
| `copy/es.json`, `copy/en.json` | Captions (voseo Spanish and English), plan badges, feature-graphic text |
| `templates/screen.html` | **Editable** screenshot template: `apple` (generic frame) and `google` (frameless) layouts |
| `templates/feature-graphic.html` | **Editable** Google Play feature graphic (1024×500), brand only |
| `scripts/compose.mjs` | Renders templates with headless Chrome/Edge at exact size, then flattens to opaque RGB PNG |
| `scripts/validate.mjs` | Checks sizes, alpha, counts, Google's side, ratio and 20% caption limits, banned phrases and provenance |
| `scripts/png.mjs` | Dependency-free PNG reader/writer (alpha detection, RGB re-encode) |
| `scripts/store-assets.test.mjs` | Tests (no browser needed) |
| `raw/` | Real captures, laid out as in `CAPTURE.md` (empty until #287) |
| `output/preview/` | Layout proofs with placeholders and a watermark; git-ignored; never uploadable |
| `output/final/` | The upload set (post-#287). Every PNG has a `.json` provenance file and the `.html` it was rendered from |

Colors come from `/DESIGN.md` through the native token parser (`native/design-tokens/generate.mjs`),
so the store images use the same palette as the apps. The brand mark is the app icon,
`frontend/resources/icon.png`.

## Requirements

- Node 20 or later (no npm packages).
- Chrome, Edge or Chromium. They are found automatically on Windows, macOS and Linux; override with `DINCR_BROWSER=<path>`.
- Fonts come from the machine that renders. Render the final set on one machine, preferably a Mac
  (SF Pro), so every image uses the same font.

## Regenerate

From the repository root:

```bash
node --test jarvis-personal/store-assets/scripts/store-assets.test.mjs
node jarvis-personal/store-assets/scripts/compose.mjs --mode preview
node jarvis-personal/store-assets/scripts/validate.mjs --dir output/preview --allow-preview
```

Useful flags: `--targets apple-iphone-69,google-phone`, `--locales es`.

After #287 is merged:

1. Capture the raw screens (`CAPTURE.md`).
2. In `config/screens.json`, confirm each screen: set `confirmed: true` and fill `how_to_reach`. Remove any screen the app doesn't have.
3. Open the gate: set `release_gate.status` to `"released"`.
4. Compose and validate:
   ```bash
   node jarvis-personal/store-assets/scripts/compose.mjs --mode final --source-commit <sha of the captured build, on origin/main>
   node jarvis-personal/store-assets/scripts/validate.mjs
   ```
5. Review every image by eye: real UI, synthetic data only, clean status bar, captions true for the plan shown.
6. Commit `raw/` and `output/final/` in a PR. Uploading to the stores is a separate, human step.

## Editing

- **Captions:** edit `copy/*.json`. Keep titles to 48 characters or fewer and subtitles to 60 or fewer. The validator
  rejects calls to action, rankings, "new"/"nuevo" and similar.
- **Layout:** edit `templates/*.html`. Sizes use `--u` (1/100 of the width), so one template serves
  iPhone, iPad and Play. Re-run the preview and the validator: Google's caption band must stay ≤ 20%.
- **Sizes:** only after re-auditing the store pages, in `config/targets.json` and `REQUIREMENTS.md`.
