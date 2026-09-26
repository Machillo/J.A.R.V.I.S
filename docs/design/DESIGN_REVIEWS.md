# DINCR design reviews — findings ledger

Every design review of DINCR records: tool and version, target, finding, severity, rationale,
decision (accepted / rejected), resulting change and re-audit status. Severity scale:
**blocker** · **important** · **moderate** · **polish**.

## Tools

| Tool | Source | Version pinned | Install |
|------|--------|----------------|---------|
| Impeccable | `github.com/pbakaus/impeccable` (Apache-2.0) | commit `9d715cc4f5564a990ca8345abfdd5df6dc9b41c8`, skill 4.4.0, engine 0.1.6 | Skill folder copied to `~/.claude/skills/impeccable`; no hooks, no project files, engine binary checksum-verified by its launcher |
| UI/UX Pro Max | `github.com/nextlevelbuilder/ui-ux-pro-max-skill` (MIT) | commit `dcc40ff5133ef78276117db0cc34e7b83cc8aeba` | Skills `ui-ux-pro-max` and `design-system` copied to `~/.claude/skills`; scripts are local Python over bundled CSV data (no network) |
| dataviz validator | Claude Code bundled `dataviz` skill | 2.1.281 bundle | `scripts/validate_palette.js` |

Scope rule (from the migration brief): the tools are **reviewers**, not authority to redesign.
Impeccable's new-work flow (concept-seed roll, image comps, decision page) was **not** used;
DINCR 2.0 was derived from the incumbent system, PRODUCT.md and the brief, then audited.

---

## Review R1 — DINCR 2.0 Design System (DESIGN.md v2.0.0 draft)

Targets: `DESIGN.md`, `docs/design/DESIGN_SYSTEM.md`, `PRODUCT.md`.

### R1.a UI/UX Pro Max — generation runs (input, not authority)

| Run | Query | Result | Assessment |
|-----|-------|--------|------------|
| 1 | `personal finance budgeting debt mobile app trustworthy calm --design-system` | Glassmorphism; trust blue `#1E40AF` + profit green `#059669` on `#0F172A`; **Caveat / Quicksand (handwritten)** | Typography misrouted (matched "personal"): rejected. Glass conflicts with Impeccable craft floor and iOS materials rule: rejected. Blue + green on navy: consistent with incumbent, informed the palette. |
| 2 (retry, narrower) | `fintech banking app dashboard --design-system --variance 3 --motion 3 --density 6` | Minimalism & Swiss; navy/trust; amber `#F59E0B` primary + violet accent; IBM Plex Sans | Style direction accepted (restrained, grid, high contrast). Amber primary + violet rejected (gold reads as VIP/premium, violet as "tech"; neither matches "calm, trustworthy"). IBM Plex rejected for native (system faces required for Dynamic Type) — see disagreement D2. |
| stack | `--stack swiftui`, `--stack jetpack-compose` | Dynamic Type via text styles, accessibility labels, `navigationDestination`, Material 3 tokens, `colorScheme` | Accepted; reflected in DESIGN_SYSTEM §2, §7. |

### R1.b Findings

| # | Tool | Finding | Severity | Rationale | Decision | Resulting change | Re-audit |
|---|------|---------|----------|-----------|----------|------------------|----------|
| 1 | UI/UX Pro Max (pro-rules: non-text contrast) | Input boundaries used `line`/`line-strong` (1.6–1.8:1); control boundaries need ≥ 3:1 | important | WCAG 1.4.11; fields invisible for low-vision users | Accepted | New `field-border` token (light `#7A889E`, dark `#65758F`, ≥ 3.17:1 on all layers); inputs use it; test gate added | PASS (`test:design-tokens`) |
| 2 | UI/UX Pro Max (`error-summary`, High) | Only "focus first invalid field"; no summary for multi-error forms | important | Screen-reader users miss other errors | Accepted | DESIGN.md Inputs: error summary + focus | PASS (spec) |
| 3 | UI/UX Pro Max (`gesture-alternative`, `dragging-alternative`, High) | Row swipe actions could become the only path to edit/delete | important | Motor and screen-reader access | Accepted | Money row: swipe is a shortcut only | PASS (spec) |
| 4 | UI/UX Pro Max (`focus-states`) | No focus ring token for hardware keyboard / switch control | moderate | iPad keyboards, Android keyboards | Accepted | `focus-ring` token + rule | PASS (spec) |
| 5 | UI/UX Pro Max (pro-rules scrim) | No scrim token | moderate | Legibility of sheets over content | Accepted | `scrim` token + opacities | PASS (spec) |
| 6 | UI/UX Pro Max (icon sizing tokens) | Icon sizes not tokenized | moderate | Rhythm consistency | Accepted | `icon.sm/md/lg/xl` | PASS (spec) |
| 7 | UI/UX Pro Max (`contextual-live-badge-updates`) | Unprompted status changes (offline, recovered queue) not announced | moderate | Screen-reader users miss state | Accepted | DESIGN_SYSTEM §7 announcements | PASS (spec) |
| 8 | UI/UX Pro Max (`no-emoji-icons`) | Capacitor currency picker uses flag emoji | polish | Font-dependent, not tokenizable | Accepted | DESIGN_SYSTEM §10: currency by code + symbol | PASS (spec) |
| 9 | Impeccable (ios.md "platform controls"; audit.native Conformance) | Spec proposed a "toast-like overlay" on iOS | important | Toasts are not an iOS component; reads as a web port | Accepted | iOS transient feedback = in-place result + haptic + inline status row | PASS (spec) |
| 10 | Impeccable (audit.native Adaptivity) | No iPad / tablet / orientation / keyboard rules | important | Capacitor ships iPad and all orientations; losing them is a parity regression | Accepted | DESIGN_SYSTEM §2 size classes, orientation, keyboard | PASS (spec) |
| 11 | Impeccable (audit.native Theming) | Raw hex tokens with no rule for native semantic assets / Increased Contrast | moderate | Hard-coded colors break increased contrast | Accepted | DESIGN.md: asset catalog (Any/Dark/Increased Contrast) + `ColorScheme` roles | PASS (spec) |
| 12 | Impeccable (craft floor: eyebrow ban) | Incumbent app uses uppercase kickers everywhere ("TU PANORAMA", "DINCR · FREE") | important | Noise; competes with headings; not native | Accepted | DESIGN.md Named Rule "No eyebrows"; plan shown as badge | PASS (spec) — incumbent Capacitor not changed |
| 13 | Impeccable (craft floor: progress rings, glass, gradients) | Incumbent uses progress ring (debts), glow gradients, glass surfaces | important | Decoration standing in for content | Accepted | Linear progress with text; tonal surfaces; no gradients | PASS (spec) |
| 14 | Impeccable (craft floor: hero-metric template) | "Big number + small label" at top of screens | moderate | Default category scaffold | **Rejected (with rationale)** | The single key figure ("Disponible este mes") is the answer to the user's primary task (PRODUCT principle 2). Kept as exactly one figure per screen; the supporting stat-tile grid is refused | n/a |
| 15 | Impeccable (android.md Dynamic Color) | Spec turns Dynamic Color off | moderate | android.md: "where it fits, with static fallback" | **Rejected (with rationale)** | Brand tint must stay identical across iOS/Android/web and its contrast pairs are validated; wallpaper-derived tints would vary per user and are unvalidated against the status colors | n/a |
| 16 | Own check (dataviz validator) | First income teal `#0B7F75` failed chroma floor (0.092) | important | Reads as gray; series identity lost | Accepted | `#008C7A` / dark `#23A897`; all six checks PASS both modes | PASS |
| 17 | Own check | Account-deletion wording contradictory | polish | Clarity | Accepted | Rewritten; no typed/long-press confirmation | PASS |

### R1.c Disagreements between the two tools

| # | Topic | UI/UX Pro Max | Impeccable | Resolution | Basis |
|---|-------|---------------|------------|------------|-------|
| D1 | Glassmorphism | Run 1 recommends it for "financial dashboards" | Bans glass as decoration; iOS allows only system materials | No glass; system materials for bars only | Platform conventions + consistency |
| D2 | Typeface | IBM Plex Sans for fintech | Lists IBM Plex among training-data defaults; product UI → system faces; iOS/Android references require SF/Roboto for body and controls | System faces (SF Pro, Roboto) with tabular digits | Accessibility (Dynamic Type / sp) + platform conventions |
| D3 | Headline number | Pattern "Trust & Authority" favors stats/proof blocks | Refuses hero-metric template | One key figure per screen, no stat grid | Product purpose (finding 14) |
| D4 | Primary color | Run 2: amber primary + violet accent | Restrained: one accent for actions/selection only | Single deep-teal tint | Consistency with incumbent mint/teal + landing teal; calm |

### R1 verdict

No blocker or important finding remains open. Two moderate findings rejected with written
rationale (14, 15). Re-audit of the rendered system happens in R2 (representative native
prototype) — a spec cannot prove rendered contrast, Dynamic Type behavior or platform feel.

---

## Review R1-final — final audit of DESIGN.md v2.0.0 (before merge)

Targets: `DESIGN.md`, `docs/design/DESIGN_SYSTEM.md`, `PRODUCT.md`, the contrast gate, compared with
the parity audit (C1), the landing (C3) and the native prototype (C4) branches as they stood at
this review.

### Tools

| Tool | Status in this review |
|------|-----------------------|
| Impeccable (`9d715cc…`) | **Not run.** Not installed in the environment of this review (checked `~/.claude/skills`, plugin directories, the repository `.claude/`, and the account's skills and plugins). The pinned commit could not be re-verified here. Equivalent manual review below uses its R1 checklists (platform controls, adaptivity, theming, craft floor). |
| UI/UX Pro Max (`dcc40ff…`) | **Not run**, same reason. Manual review used its R1 rules (non-text contrast, error summary, gesture alternatives, focus states, scrim, icon tokens, live announcements). |
| dataviz validator (2.1.281) | Re-run: light `#008C7A,#5B63C9` and dark `#23A897,#7A80E0` — all checks PASS (CVD ΔE 16.2 / 13.7 deutan, normal 20.0 / 19.2). |
| `test:design-tokens` | Re-run with mutations (below). |

### Status of R1 findings

| # | Severity | Status | Note |
|---|----------|--------|------|
| 1 | important | RESOLVED | `field-border` gated ≥ 3:1 on every neutral layer, both modes |
| 2 | important | RESOLVED | Error summary (DESIGN.md Inputs, §16) |
| 3 | important | RESOLVED | Swipe is a shortcut only (DESIGN.md Money row) |
| 9 | important | RESOLVED | iOS status row instead of toast (§2, §18) |
| 10 | important | RESOLVED, corrected | iPad/orientation/keyboard rules; iPad sidebar now correctly gated to iOS 18 (R1F-3) |
| 12 | important | ACCEPTED for native and landing; DEFERRED for the Capacitor app | Capacitor still shows eyebrows; migration is out of scope of the design system |
| 13 | important | ACCEPTED for native and landing; DEFERRED for the Capacitor app | Capacitor still has the progress ring, gradients and glass |
| 16 | important | RESOLVED | Chart pair validated; now also enforced pairwise by the gate (R1F-1) |
| 4–8, 11, 17 | moderate / polish | RESOLVED | 11 reworded: generated dynamic colors are allowed with the increased-contrast mapping (§7) |
| 14 | moderate | REJECTED WITH RATIONALE | One key figure is the answer to the primary task; stat grids stay refused |
| 15 | moderate | REJECTED WITH RATIONALE | Dynamic Color off: the tint and its contrast pairs must be identical and validated on every platform |

Disagreements D1–D4 stand as recorded above: each was resolved by an explicit decision, not by
the tools agreeing.

### New findings (manual review)

| # | Finding | Severity | Decision / change |
|---|---------|----------|-------------------|
| R1F-1 | Gate did not fail when two chart series collided (mutation passed) | important | RESOLVED: pairwise OKLab ΔE check (normal ≥ 15, protan/deutan ≥ 8) |
| R1F-2 | Gate crashed on CRLF checkouts (Windows, `core.autocrlf=true`); silently skipped malformed or unpaired color tokens | important | RESOLVED: CRLF normalized; every color line must parse; every color must be in a pair or an exemption with a reason |
| R1F-3 | §9 justified iOS 17 with the `TabView` sidebar, but `.sidebarAdaptable` needs iOS 18 | important | RESOLVED: iPad sidebar gated by `#available`; iOS minimum left as a product decision with analysis (§9) |
| R1F-4 | CI workflow did not trigger on a change to the root `DESIGN.md` only, so the gate could be skipped | important | RESOLVED: `DESIGN.md` added to the workflow paths |
| R1F-5 | Supporting text on status containers and the selected-chip icon were not gated | moderate | RESOLVED: pairs added (all pass) |
| R1F-6 | Android `motion-instant` used an accelerate curve while iOS uses decelerate | moderate | RESOLVED: `LinearOutSlowInEasing` |
| R1F-7 | Android `CONFIRM` / `REJECT` haptics need API 30; minSdk is 24 | moderate | RESOLVED: no-haptic fallback below API 30 (§6) |
| R1F-8 | §12 said landing properties are generated from DESIGN.md; they are hand-copied | moderate | RESOLVED in wording; sync check is follow-up work for the landing |
| R1F-9 | Missing rules: touch targets per control, component states, forms, numeric presentation, feedback choice, navigation / deep links / badges, security and privacy UX, typography roles, versioning | important | RESOLVED: §13–§21 and "Versioning and native synchronization" |
| R1F-10 | Motion, disabled opacity, elevation and scrim opacity exist only as prose, so native generators cannot emit them | moderate | DEFERRED: promote to frontmatter in a minor version together with generator support; values stay normative in DESIGN_SYSTEM.md until then |
| R1F-11 | Increased Contrast required named assets with an extra appearance but no token set exists | moderate | RESOLVED: mapped onto existing tokens (§7); DESIGN.md prose aligned |
| R1F-12 | Focus ring equals the tint | polish | ACCEPTED: the 2 pt offset gap separates it from filled tint controls (§7) |

### Compatibility

- **Parity audit (C1)**: the navigation labels match the Capacitor tabs. Gaps found (deep-link /
  OAuth return, app lock and biometric failure, mail reconnection, candidate review controls,
  badges, recovering mode) are now covered by §14, §15, §18–§20. Screens outside the design
  system (onboarding content, support, export) follow the generic states. `PRODUCT.md` and §3
  cite `docs/native/` files that exist only on the parity-audit branch.
- **Landing (C3)**: all color values match the tokens in both schemes. Differences recorded for
  the landing brief: property names differ from token names, one duplicate and two unused
  properties, off-scale radii (8, 12, 32), progress bar radius, button padding and weight, a
  150 ms transition, page-load entrance motion and a blurred header (landing exceptions not yet
  documented), and warning color on a launch notice. No hand-off sync check exists yet.
- **Native prototype (C4)**: colors, spacing, radii and icon sizes are generated and match; the
  generator's `--check` passes against this version of DESIGN.md (the frontmatter is unchanged).
  Differences are prototype-side drift, not mapping failures: Android lacks a top app bar,
  `NavHost`, secondary/destructive buttons and motion tokens; some Android type roles differ;
  iOS sheet detents and icon sizes; Android money text can truncate; "+₡0" for zero. The iPad
  sidebar contradiction was in this document and is fixed.
- **Capacitor web app (sample: Home, Finance, Transactions, Mail automation, Settings)**:
  legacy UI to migrate. Expenses in coral/red, uppercase eyebrows, per-plan palettes, gradients,
  glass and a progress ring are *intentionally changed* by DINCR 2.0; visible field labels and
  in-place mail-review feedback are *compatible*. Rewriting the web app is out of scope.

### R1-final verdict

No important finding is open inside the design system. Open human decisions: the iOS minimum
(§9) and the PRODUCT.md inferences listed in its "Fact status". A rendered review (R2/R3 on
devices) is still required: a specification cannot prove Dynamic Type behavior, rendered contrast
or platform feel.
