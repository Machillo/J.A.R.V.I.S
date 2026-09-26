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
