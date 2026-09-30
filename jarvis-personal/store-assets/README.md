# DINCR store assets (App Store / Google Play)

This pipeline produces store screenshots from **real captures of the native DINCR app** (PR #287,
merged into `main`) running on synthetic data, with DINCR branding and ES/EN captions, at the exact
sizes each store requires. It validates them before anyone uploads them. **Nothing here uploads
or publishes anything.**

## Status (2026-09-29)

| Set | State |
|---|---|
| Google Play, ES (`es-419`) and EN (`en-US`) | **Final**: 8 phone screenshots per language (1440×2560) + feature graphic (1024×500), from Android captures. `output/final/google/` |
| App Store, iPhone 6.9" and iPad 13" | **MAC REQUIRED**: not captured yet. Since #294 the iOS app has the same 8 store screens as Android, and the capture test navigates them (`StoreScreenshots.swift`). See `CAPTURE.md` |

**Human gate before uploading (not a screenshot decision):** the stores still ship the Capacitor
app. These images show the native app, so they may be uploaded only when the native build takes the
store identity (`native/RELEASE_IDENTITY.md`). Run `validate.mjs --require-main` right before
uploading: it also requires the captured app commit to be on `origin/main`.

## Layout

| Path | What it is |
|---|---|
| `REQUIREMENTS.md` | Audit of the current Apple and Google rules (sources, date) and the decisions derived from them, including the iPad note |
| `CAPTURE.md` | How captures are made: Android (automated, any OS) and iOS (MAC REQUIRED), fixture and data rules |
| `config/screens.json` | The store screens in order, per platform (available, confirmed, how to reach), each screen's plan, the #287 baseline commit and the fixture |
| `config/targets.json` | Output sizes, counts and store rules (banned phrases, caption ≤ 20%, no alpha) |
| `copy/es.json`, `copy/en.json` | Captions (voseo Spanish and English), plan badges, feature-graphic text |
| `templates/screen.html` | **Editable** screenshot template: `apple` (generic frame) and `google` (frameless card) layouts |
| `templates/feature-graphic.html` | **Editable** Google Play feature graphic (1024×500), brand only |
| `scripts/capture-android.mjs` | Builds, installs and runs the opt-in capture test on an emulator; writes `raw/android/` and its manifest |
| `scripts/capture-ios.mjs` | Same for iOS simulators (MAC REQUIRED) |
| `scripts/compose.mjs` | Renders templates with headless Chrome/Edge at exact size (two identical renders required), then flattens to opaque RGB PNG |
| `scripts/validate.mjs` | Checks sizes, alpha, counts, Google's side, ratio and 20% caption limits, banned phrases, plan badges and provenance |
| `scripts/png.mjs` | Dependency-free PNG reader/writer (alpha detection, RGB re-encode) |
| `scripts/store-assets.test.mjs` | Tests (no browser, emulator or simulator needed); CI runs them in the Native apps workflow |
| `raw/<android\|ios>/` | Real captures (`<es\|en>/<phone\|tablet>/<screen>.png`) and `capture-manifest.json` |
| `output/final/` | The upload set. Every PNG has a `.json` provenance file and the `.html` it was rendered from |
| `output/preview/` | Layout proofs with placeholders and a watermark; git-ignored; never uploadable |

Colors come from `/DESIGN.md` through the native token parser (`native/design-tokens/generate.mjs`).
The brand mark is the app icon, `frontend/resources/icon.png`.

## What makes an image final

`compose.mjs --mode final` refuses, and `validate.mjs` rejects, unless:

- the captured app commit **contains the #287 merge** (`app_baseline` in `screens.json`; anything
  older shows the Capacitor UI) and is in the checked-out history (with `--require-main`: on `origin/main`);
- the screen is **confirmed for that platform** in `screens.json`;
- the capture manifest comes from a run that **built the app from a clean tree** of that commit with
  the **STORE** fixture, and each capture's **SHA-256** still matches it;
- the captured platform's app has not changed since the captured commit: `native/` except the other
  platform's tree (a Google image goes stale with `native/android/**` or shared native code such as
  `design-tokens/`, never with `native/ios/**`, and the reverse for Apple); and copy, templates, config
  and brand have not changed since the image was composed (else it is stale: re-capture or re-compose);
- the capture was taken with the **screen's plan**, and the caption carries that plan's badge;
- the PNG is the exact size, **without alpha**, and not a preview or placeholder;
- the provenance file exists, the image's own SHA-256 matches it, its capture is exactly
  `raw/<platform>/<language>/<device>/<screen>.png` and agrees with the capture manifest, and the
  `.html` source has no local `file://` path. The validator re-checks all of this; it does not trust
  the provenance file alone.

**Merge note.** Provenance names commits of this branch. Merge the PR with a merge commit (not a
squash), or re-capture from `main` afterwards; otherwise `validate.mjs --require-main` cannot pass.

Provenance per image (`.json`): image SHA-256, mode, store, platform, locale, screen, plan, size,
alpha, caption band, capture (file, SHA-256, fixture, fixture date, capture time, device), source
(app) commit, #287 baseline, pipeline commit, generation time.

## Regenerate

From the repository root. Android captures (Windows, macOS or Linux, emulator running, JDK 17):

```bash
node jarvis-personal/store-assets/scripts/capture-android.mjs
```

Compose and validate the Google Play set (the source commit is the one in `raw/android/capture-manifest.json`):

```bash
node jarvis-personal/store-assets/scripts/compose.mjs --mode final --targets google-phone,google-feature-graphic --source-commit <sha>
node jarvis-personal/store-assets/scripts/validate.mjs --targets google-phone,google-feature-graphic
```

iOS: `CAPTURE.md` → MAC REQUIRED. Then compose with `--targets apple-iphone-69,apple-ipad-13` and the iOS manifest's commit.

Tests and layout proofs:

```bash
node --test jarvis-personal/store-assets/scripts/store-assets.test.mjs
node jarvis-personal/store-assets/scripts/compose.mjs --mode preview
node jarvis-personal/store-assets/scripts/validate.mjs --dir output/preview --allow-preview
```

Review every image by eye before a PR: real UI, synthetic data only, clean status bar, captions true
for the plan shown. Uploading to the stores is a separate, human step.

## Editing

- **Captions:** edit `copy/*.json`. Titles ≤ 48 characters, subtitles ≤ 60. The validator rejects
  calls to action, rankings, "new"/"nuevo" and similar, and a badge that does not match the screen's plan.
- **Screens:** edit `config/screens.json` **and** the capture tests (`StoreScreenshots.kt`,
  `StoreScreenshots.swift`); a test checks they list the same screens and plans. Never add a
  screen the app does not have.
- **Data:** the STORE fixture is `native/android/core/data/.../StoreSample.kt`; iOS reads the same
  account from `store-sample.json` (`native/ios/DincrKit/Sources/DincrCore/StoreSample.swift`,
  served by `FixtureBackend` `.store`). What the backend computes from it (strategy, VIP command
  center, guided budget, Free dashboard) is never hand-written: it lives in
  `native/android/core/data/src/main/resources/store-sample.json` and its byte copy
  `native/ios/DincrKit/Sources/DincrCore/Resources/store-sample.json`, both written and checked by
  the backend engines (`backend/tests/test_store_sample_engine.py`). After changing the data:
  `DINCR_UPDATE_STORE_GOLDEN=1 ./gradlew :core:data:test` (Android), then
  `DINCR_UPDATE_STORE_GOLDEN=1 python -m pytest backend/tests/test_store_sample_engine.py` (from `jarvis-personal`), then re-capture.
- **Layout:** edit `templates/*.html`. Sizes use `--u` (1/100 of the width), so one template serves
  iPhone, iPad and Play. Re-run the preview and the validator: Google's caption band must stay ≤ 20%.
- **Sizes:** only after re-auditing the store pages, in `config/targets.json` and `REQUIREMENTS.md`.
