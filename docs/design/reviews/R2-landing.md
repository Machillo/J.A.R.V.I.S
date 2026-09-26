# Review R2 — Landing (dincr.com), 2026-09-25

Target: `jarvis-personal/frontend/landing/` (`style.css`, `build.mjs`), built pages `/`,
`/precios/`, `/descargar/`. Mode: *Persuade* surface, web, JavaScript-free by contract.
Tools: Impeccable `9d715cc` (engine 0.1.6, `impeccable detect`), UI/UX Pro Max `dcc40ff`
(landing and UX domains). Ledger format: see `docs/design/DESIGN_REVIEWS.md` (PR C2).

## Baseline (before)

`impeccable detect` on `index.html` + `style.css`: 13 warnings.

| # | Tool | Finding | Severity | Decision | Change | Re-audit |
|---|------|---------|----------|----------|--------|----------|
| L1 | Impeccable detect `low-contrast` (×3) | Light mode primary buttons: white on `#0d9488` = **3.7:1** (needs 4.5:1) | **blocker** (WCAG AA failure on the main CTA) | Accepted | Landing adopts DINCR 2.0 tokens: light `#0B6E68`/white = 6.10:1, dark `#3CCFBF`/`#04201D` = 8.84:1 | PASS (0 findings) |
| L2 | Impeccable detect `hero-eyebrow-chip` + craft floor eyebrow ban | Tracked-caps kicker above H1 and above every H2 (11 eyebrows) | important | Accepted | Eyebrows removed; "Costa Rica" moved into the lead sentence | PASS |
| L3 | Impeccable detect `all-caps-body` | Uppercase body text (eyebrows, footer headings, badges) | moderate | Accepted | Sentence case everywhere | PASS |
| L4 | Impeccable detect `side-tab` | 3 px gold `border-left` on the problem list | moderate | Accepted | Neutral rows with a drawn warning icon | PASS |
| L5 | Impeccable detect `overused-font` | `Inter` declared but never loaded (renders per-machine) | moderate | Accepted | System UI stack (SF Pro / Segoe / Roboto), matching the native apps; no web-font request (privacy, performance) | PASS |
| L6 | Impeccable craft floor (glyphs as icons) | "✓" and "+/–" Unicode glyphs as icons | moderate | Accepted | Drawn SVG icons (Lucide geometry) applied as CSS masks in token colors; table marks have `role="img"` + labels | PASS |
| L7 | Own check vs DESIGN.md | Landing palette (teal `#14b8a6`, gold) diverged from the app | important | Accepted | Same tokens as `/DESIGN.md` in both schemes | PASS |
| L8 | Impeccable detect `gpt-thin-border-wide-shadow` (appeared after first pass) | 1 px border + 24 px shadow on the non-floating illustration and on the menu | moderate | Accepted | Shadow only on floating elements (menu, no border); illustration flat | PASS |
| L9 | Impeccable detect `cramped-padding` (×8) | "children flush against bg/border" on `.section`, `.band`, `.faqs`, `.footer-legal`, `.table-wrap` | — | **Rejected: verified false positive** | Insets come from `.wrap` inline margins (16 px), `summary` padding (12 px), caption/cell padding (12–16 px); confirmed in 375 px and desktop renders | n/a |
| L10 | Impeccable detect `flat-type-hierarchy` | Footer group headings (h2, 14.4 px) smaller than body | polish | **Rejected** | Footer headings are group labels by design; page headings keep a 1.25+ ratio | n/a |
| L11 | Impeccable detect `em-dash-overuse` (`/precios/`) | 9 "—" in body text | — | **Rejected: false positive** | They are "No incluido" table marks with `role="img"` and labels | n/a |
| L12 | UI/UX Pro Max `landing: app-store-style-landing` | Device mockup + real screenshots carousel + ratings | moderate | **Deferred** | Real captures do not exist yet; the hero keeps the labeled illustration (contract test). Native prototype (C4) will produce synthetic-data captures for `heroScreenshot`. Ratings: none exist — never fabricated. Carousel: rejected (motion + a11y cost, one screenshot suffices) | open (C4) |
| L13 | UI/UX Pro Max `landing: waitlist-coming-soon` | Email capture + countdown | moderate | **Rejected** | Countdown conflicts with "calm over urgency"; email capture needs a backend and privacy review (Agent A scope), and the site is JS-free by contract | n/a |
| L14 | UI/UX Pro Max `ux: motion` ("animate 1–2 key elements per view", reduced motion) | No motion at all; no press feedback | moderate | Accepted | One authored moment: the product illustration settles in and the budget bar fills, only under `prefers-reduced-motion: no-preference`; button hover/press (150 ms / scale .98); FAQ chevron rotation | PASS |
| L15 | Brief (platform sections) | `/descargar/` showed only one sentence | important | Accepted | Platform cards (Android, iPhone): sign-in methods, lock options, minimum OS — each verified against code (`Login.jsx`, `appLock.js`, `minSdk 24`, iOS deployment target 15) | PASS |

## After

`impeccable detect` on `/`, `/precios/`, `/descargar/` + `style.css`: only the rejected
false positives (L9–L11) remain. `npm run test:landing` passes.

## Visual evidence

In-app browser (Claude desktop), 375×812 dark and light, desktop width dark: hero, problem list,
steps, features, pricing table, download page. Headless full-page captures were not possible
(no Chrome installed; Playwright browsers were not installed, to avoid another third-party download).

## Disagreements

| Topic | Impeccable | UI/UX Pro Max | Resolution |
|-------|------------|---------------|------------|
| Display face on a Persuade page | Wants a face with a point of view; system face flagged as fallback | Neutral | System stack kept: brand consistency with the native apps, no third-party font request on a no-tracking site; revisit only with a licensed, self-hosted face |
| Page pattern | Refuses category templates | Recommends app-store template | Structure unchanged (content-led sections already pass); screenshots deferred to real captures |

## Final audit (R2.1, 2026-09-26)

Impeccable and UI/UX Pro Max were **not installed** in the environment of this pass, so they were
not re-run; the same checklists were applied by hand to the built HTML and CSS and the site was
rendered in the in-app browser (320, 360, 375, 390, 430, 768, 1280 px; light and dark).

Status of L1–L15: L1–L5, L7, L8, L14, L15 **RESOLVED** (re-checked in code and render). L6
**RESOLVED, revised**: table marks no longer use `role="img"` on empty spans; the icon is
`aria-hidden` and the cell carries visually hidden text ("Incluido" / "No incluido"). L9
**REJECTED, false positive confirmed** (16 px `.wrap` gutters, summary and cell padding visible
in every render). L10 **REJECTED with rationale** (footer group labels). L11 **REJECTED, false
positive** (the "—" marks are decorative, with text alternatives). L12 **DEFERRED** (real captures,
C4). L13 **REJECTED** (unchanged rationale).

| # | Source | Finding | Severity | Decision | Change | Re-audit |
|---|--------|---------|----------|----------|--------|----------|
| L16 | Render 320–430 px | `/precios/` comparison table had `min-width: 520px`: at phone widths the Free/Basic/VIP columns started off-screen, and the new visually hidden cell text widened the page to 518 px | important | Accepted | No min-width; tighter cell padding below 640 px; `.table-wrap` is the containing block | PASS: no horizontal overflow on any route at 320–1280 px |
| L17 | Manual (forced colors) | CSS-mask icons are painted with `background`, which forced-colors mode replaces, so the table checks, FAQ chevron and list icons vanished in Windows high contrast | important | Accepted | `@media (forced-colors: active)` paints them in `CanvasText` | Contract test; not rendered in forced colors (HUMAN) |
| L18 | Claim audit | `/soporte/` sent users to "la sección Reportes" for help; in the app, Reportes is financial reports and help is "Ayuda y soporte" | important | Accepted | Copy fixed | Contract test |
| L19 | Claim audit | Android lock copy said "huella o PIN"; the code uses `BIOMETRIC_WEAK` + device credential (PIN, pattern or password) | moderate | Accepted | "biometría del teléfono (como la huella) o con su PIN, patrón o contraseña" | PASS |
| L20 | Claim audit | "Una sola cuenta DINCR en los dos sistemas" is only true when the same sign-in is used (a different sign-in, e.g. Apple with "Hide My Email" on iPhone and Google on Android, can produce a different account) | moderate | Accepted | "Si entrás con la misma cuenta en los dos sistemas…" | PASS |
| L21 | Own check vs #270 | Tokens were copied by hand with no drift control | moderate | Accepted | Each CSS color names its DESIGN.md token; `test:landing` checks AA for every text/control pair and, when DESIGN.md exists, equality with the token | PASS (checked with #270's DESIGN.md present) |
| L22 | Claim audit | "Requiere iOS 15" is true only for the current Capacitor project (deployment target 15.0); the native prototype (#279) proposes iOS 17, pending product-owner decision | important | **Accepted as guard, decision open** | `test:landing` fails if the iOS deployment target or Android `minSdk` changes without updating `/descargar/` | HUMAN release decision |
