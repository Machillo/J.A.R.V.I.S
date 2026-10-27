---
name: DINCR 3.0
description: Calm, trustworthy personal finance for iOS and Android — one identity, native on each platform.
version: 3.0.0
colors:
  # Light scheme
  bg: "#F2F5F9"
  surface: "#FFFFFF"
  surface-2: "#E8EDF4"
  line: "#DCE3EC"
  line-strong: "#C2CCDA"
  field-border: "#6F7E96"
  focus-ring: "#0A6B5C"
  scrim: "#081324"
  text: "#0A1628"
  text-2: "#3F4D66"
  text-muted: "#56647C"
  tint: "#0A6B5C"
  tint-pressed: "#075447"
  tint-container: "#D2F0E7"
  on-tint: "#FFFFFF"
  on-tint-container: "#03372E"
  positive: "#07724E"
  positive-container: "#D7F2E5"
  negative: "#B3233D"
  negative-container: "#FBE1E6"
  warning: "#965500"
  warning-container: "#FCEBCE"
  info: "#0A5A8C"
  info-container: "#DCEDF9"
  vip: "#845600"
  vip-container: "#F6EACD"
  chart-income: "#0A8C76"
  chart-expense: "#5B63C9"
  hero: "#0C1C36"
  hero-2: "#17294A"
  on-hero: "#FFFFFF"
  on-hero-2: "#B8C6DC"
  hero-accent: "#6FE3CB"
  # Dark scheme
  dark-bg: "#070E1A"
  dark-surface: "#0F1A2B"
  dark-surface-2: "#172539"
  dark-line: "#22324A"
  dark-line-strong: "#33445F"
  dark-field-border: "#6A7A94"
  dark-focus-ring: "#45D3BC"
  dark-scrim: "#000000"
  dark-text: "#EDF2F9"
  dark-text-2: "#B3C0D2"
  dark-text-muted: "#94A3B9"
  dark-tint: "#45D3BC"
  dark-tint-pressed: "#33B9A4"
  dark-tint-container: "#0C3A34"
  dark-on-tint: "#03201B"
  dark-on-tint-container: "#C0F2E8"
  dark-positive: "#4ADE9A"
  dark-positive-container: "#0D3524"
  dark-negative: "#FF8A9B"
  dark-negative-container: "#3E1520"
  dark-warning: "#F5B94A"
  dark-warning-container: "#3A2A0B"
  dark-info: "#7CC8F5"
  dark-info-container: "#0E2F45"
  dark-vip: "#E3BD6A"
  dark-vip-container: "#3A2C0C"
  dark-chart-income: "#23A897"
  dark-chart-expense: "#7A80E0"
  dark-hero: "#11264A"
  dark-hero-2: "#1A3360"
  dark-on-hero: "#FFFFFF"
  dark-on-hero-2: "#BACAE3"
  dark-hero-accent: "#6FE3CB"
typography:
  # Native apps use the platform text styles (Dynamic Type / sp). Sizes are the default
  # (100%) size; they scale with the user's setting. Money uses tabular figures.
  display-amount:
    fontFamily: "SF Pro Display (iOS) / Roboto (Android)"
    fontSize: "34pt"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.01em"
  title-1:
    fontFamily: "SF Pro (iOS .title2) / Roboto (Android headlineSmall)"
    fontSize: "22pt"
    fontWeight: 700
    lineHeight: 1.27
  title-2:
    fontFamily: "SF Pro (iOS .headline) / Roboto (Android titleMedium)"
    fontSize: "17pt"
    fontWeight: 600
    lineHeight: 1.29
  body:
    fontFamily: "SF Pro (iOS .body) / Roboto (Android bodyLarge)"
    fontSize: "17pt"
    fontWeight: 400
    lineHeight: 1.29
  body-small:
    fontFamily: "SF Pro (iOS .subheadline) / Roboto (Android bodyMedium)"
    fontSize: "15pt"
    fontWeight: 400
    lineHeight: 1.33
  label:
    fontFamily: "SF Pro (iOS .footnote) / Roboto (Android labelLarge)"
    fontSize: "13pt"
    fontWeight: 500
    lineHeight: 1.38
  caption:
    fontFamily: "SF Pro (iOS .caption1) / Roboto (Android bodySmall)"
    fontSize: "12pt"
    fontWeight: 400
    lineHeight: 1.33
rounded:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "20px"
  sheet: "28px"
  full: "999px"
icon:
  sm: "16px"
  md: "20px"
  lg: "24px"
  xl: "28px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
  "12": "48px"
components:
  button-primary:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.on-tint}"
    typography: "{typography.title-2}"
    rounded: "{rounded.md}"
    height: "52px"
    padding: "0 20px"
  button-primary-pressed:
    backgroundColor: "{colors.tint-pressed}"
    textColor: "{colors.on-tint}"
  button-secondary:
    backgroundColor: "{colors.tint-container}"
    textColor: "{colors.on-tint-container}"
    typography: "{typography.title-2}"
    rounded: "{rounded.md}"
    height: "52px"
  button-destructive:
    backgroundColor: "{colors.negative}"
    textColor: "{colors.on-tint}"
    typography: "{typography.title-2}"
    rounded: "{rounded.md}"
    height: "52px"
  button-text:
    textColor: "{colors.tint}"
    typography: "{typography.title-2}"
    height: "44px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "16px"
  list-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    height: "56px"
    padding: "12px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    height: "52px"
    padding: "0 16px"
  chip:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    height: "36px"
    padding: "0 14px"
  chip-selected:
    backgroundColor: "{colors.tint-container}"
    textColor: "{colors.on-tint-container}"
  banner-info:
    backgroundColor: "{colors.info-container}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  message-technical-error:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  message-attention:
    backgroundColor: "{colors.warning-container}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  message-opportunity:
    backgroundColor: "{colors.tint-container}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  message-positive:
    backgroundColor: "{colors.positive-container}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  plan-badge-vip:
    backgroundColor: "{colors.vip-container}"
    textColor: "{colors.vip}"
    typography: "{typography.caption}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  sheet:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.sheet}"
    padding: "24px 16px"
---

# Design System: DINCR 3.0

Normative tokens are in the frontmatter above. The full behavioral specification (motion, haptics,
states, accessibility, charts, platform mapping, copy) is in
[`docs/design/DESIGN_SYSTEM.md`](docs/design/DESIGN_SYSTEM.md); independent reviews are in
[`docs/design/DESIGN_REVIEWS.md`](docs/design/DESIGN_REVIEWS.md).

## Overview

DINCR 3.0 is a **Restrained**, content-first system for an *Operate* product: people check what they
have, record what happened and decide the next step. Physical scene: a phone in one hand, on a bus
at 7 a.m. or on the couch at 10 p.m. — so light and dark are both first-class and **follow the
system setting by default**, with an in-app override.

The identity lives in four places and nowhere else: a single jade **tint** (actions, current
selection, focus), the deep-ink **hero card** that carries each screen's main figure, **tabular
money figures** set large and calm, and a **voice** that states money facts plainly. Everything else is the platform: SwiftUI and Material 3 components, system type,
system navigation. The previous generation's glow gradients, glass cards and per-plan re-skins are
retired.

## Colors

### Primary

- **Tint** (`tint` / `dark-tint`): the only interactive color. Primary buttons, links, selected
  tabs and chips, focus rings, progress toward a user goal. Never decoration, never a background
  wash.
- **Tint container**: tonal secondary actions and selected chips.

### Hero (DINCR 3.0)

- `hero` → `hero-2`: the deep-ink surface (a diagonal gradient between the two) of the **hero
  card**, the one card per screen that carries the main figure (Hoy → Estado de hoy). It is a
  surface, not a decoration: never behind lists, forms or warnings.
- Inside it, text uses `on-hero` (the figure) and `on-hero-2` (supporting), and nested components
  use the **dark scheme's roles** in both schemes (Android `heroPalette`, iOS dark color scheme in
  `dincrHeroCard`), so income, expense, status and progress keep their meaning and contrast. The
  contrast gate checks every one of those roles on both hero surfaces.
- `hero-accent`: small labels and highlights on the hero only (the Perfil avatar).
- Where it is used: Hoy → Estado de hoy (the main figure) and Perfil → the account header. A screen
  without a backend figure keeps a normal card; the hero never invents or computes a value.

### Neutral

- `bg` → `surface` → `surface-2`: three tonal layers. Grouped lists and cards sit on `surface`
  over `bg`; nested regions use `surface-2`. Lines separate only when spacing cannot.
- `text` (primary), `text-2` (supporting), `text-muted` (metadata). All three pass WCAG AA
  (≥ 4.5:1) on every neutral layer in both schemes.
- `line` / `line-strong` are decorative separators only. Any boundary that identifies a control
  (text fields, unselected checkboxes, outlined buttons) uses `field-border` (≥ 3:1 on every
  neutral layer, WCAG 1.4.11).
- `focus-ring`: 2 pt ring, 2 pt offset, for hardware-keyboard / switch-control focus (iPad,
  Android with keyboard). `scrim`: 40% (light) / 60% (dark) behind modal sheets and dialogs where
  the platform does not supply one.
- Native implementation: every color comes from the token set generated from this file (iOS
  dynamic colors or asset-catalog colors for Any and Dark, with the increased-contrast mapping in
  `DESIGN_SYSTEM.md` §7; Android `ColorScheme` roles for light and dark). No raw hex in screen
  code.

### Semantic (status)

| Role | Meaning | Never used for |
|------|---------|----------------|
| positive | received money, goal reached, success confirmation | decoration, "income" labels that are not a completed event |
| negative | inline error (`ErrorState`: invalid input or a failed load/save), overspent budget, overdue payment, destructive action | ordinary expenses, a financial alert (see Messages) |
| warning | a financial situation that needs attention (payment in ≤ 3 days, commitments above income, missing data the user can add) | promotions, a failure of DINCR |
| info | neutral notices (`StatusBanner`) | brand accents, a recommendation (see Messages) |
| vip | the VIP plan badge only | anything else |

Status colors always ship with an icon and text. Money is signed with `+` / `−` — never by color
alone.

### Data visualization

`chart-income` (teal) and `chart-expense` (indigo) are the two series colors. Validated with the
dataviz six-checks validator in both modes (lightness band, chroma floor, CVD ΔE ≥ 13.7 deutan,
normal-vision ΔE ≥ 19, ≥ 3:1 on surface). Single-series magnitude charts use `chart-expense` alone.

**Visualize information; do not invent information.** A chart draws values the caller already
has; it never computes, approximates or fills them in. Unknown stays "sin dato" (never 0), a period
without data is a gap (never 0 and never interpolated), a share exists only when the whole is known
and positive, and values in different currencies are never added. The models
(`DincrCore/VisualModels.swift`, `com.dincr.data.VisualModels`) enforce this and are tested.

**Direction ≠ financial meaning.** Up is not good and down is not bad: debt going down is good,
savings going down is not. A trend's direction picks the arrow; the caller says what it means
(`TrendMeaning`), and only that picks the color.

The family (shared components on both platforms, same names):

| Question | Component | Use when | Not when |
|----------|-----------|----------|----------|
| What is it made of? | `CompositionDonut` | Parts of one positive whole in one currency (debts, categories, assets); legend rows with value and %, tap a part to see it | Parts unknown, negative or in mixed currencies (it shows why, in words, instead); a single number; more parts than can be told apart without the legend |
| How did it change over time? | `TrendLineChart` | Two or more known periods; baseline at 0; tap a period to read its value | One value (say it in text); comparing two categories side by side (bars) |
| How far along? | `DincrProgressBar` | Progress toward a positive target, with the value in text next to it | Unknown or invalid target (it shows "sin dato"); decoration |
| Quick trend on a card | `Sparkline` | Next to the figure it summarizes, on Hoy-style cards; no axes; spoken summary | As the only place a value appears; analysis screens (use the line chart) |
| Better or worse than before? | `TrendIndicator` | A comparison of two known values, with the meaning given by the caller | No earlier value (it says "sin comparación") |

Don't chart when a sentence or one number answers the question faster. Every chart is readable
without the picture: screen readers get each value (and share or direction), not just a title.

### Named Rules

- **Expenses are not red.** Spending money is normal; red is reserved for problems.
- **One tint.** If a second accent seems necessary, the hierarchy is wrong.
- **Plans don't repaint the app.** Free, Basic and VIP share the palette; VIP is marked by a badge.

## Typography

System faces only: **SF Pro** on iOS, **Roboto** on Android, always through the platform text
styles so Dynamic Type and font scaling work up to the largest accessibility sizes. No custom
display face in the apps.

### Hierarchy

| Token | iOS | Android (M3) | Use |
|-------|-----|--------------|-----|
| display-amount | `.largeTitle` bold, `.monospacedDigit()` | `displaySmall` bold, `tnum` | The one key figure per screen |
| title-1 | `.title2` bold | `headlineSmall` | Screen and section titles |
| title-2 | `.headline` | `titleMedium` | Card titles, row primary text emphasis, buttons |
| body | `.body` | `bodyLarge` | Row text, form values, prose |
| body-small | `.subheadline` | `bodyMedium` | Supporting text |
| label | `.footnote` medium | `labelLarge` | Field labels, chips, tabs |
| caption | `.caption` | `bodySmall` | Metadata, dates, units |

Top-level screens use the platform large title (iOS large title collapsing on scroll; Android
medium/large top app bar).

### Named Rules

- **Tabular money.** Every amount uses tabular (monospaced) digits so columns align and values
  don't jitter while updating.
- **No eyebrows.** No uppercase kicker labels above headings ("TU PANORAMA", "DINCR · FREE").
  The heading carries its own weight.
- **Currency formatting comes from the user's profile**, not from the device locale alone and never
  hard-coded.

## Layout

- 4-pt base grid; spacing tokens `1`–`12` (4–48). Screen side margin `4` (16) on phones, readable
  width capped at 600 pt on tablets and large phones in landscape.
- More space above a section heading (`6`, 24) than below it (`2`, 8).
- One primary figure per screen, then content grouped in inset lists or cards; no stat-tile grids.
- Touch targets ≥ 44 × 44 pt (iOS) / 48 × 48 dp (Android), ≥ 8 between adjacent targets.
- Layout must hold at the largest Dynamic Type / font-scale size: rows wrap into two lines,
  horizontal pairs stack vertically.

## Elevation & Depth

- Depth is **tonal**: `bg` < `surface` < `surface-2`. Cards and lists do not cast shadows; a card
  carries a 1 px `line` edge so it reads on `bg` in bright light. The hero card has no edge.
- Only floating elements cast a shadow: sheets, menus, snackbars, the bottom bar on scroll. One
  shadow: y 8, blur 24, `#0B1526` at 12% (light) / `#000000` at 40% (dark).
- Blur and translucency come only from system materials (iOS bar and sheet materials, Android none).

## Shapes

| Token | Radius | Use |
|-------|--------|-----|
| xs | 6 | progress bar ends, small tags |
| sm | 10 | inputs, segmented controls |
| md | 14 | buttons, banners |
| lg | 20 | cards, grouped list sections |
| sheet | 28 | bottom sheets, dialogs (Android extra-large) |
| full | 999 | chips, badges, avatar, inline action pills, the Movimientos search field |

iOS uses continuous ("squircle") corners. No progress rings; progress is a linear bar with its value
in text.

## Components

### Buttons

- **Primary** (filled tint): one per screen or sheet; the action that completes the task.
- **Pill actions** (DINCR 3.0, Android `DincrPillButton` / `DincrTonalButton`): inline actions on
  a row, as in the mail review — the completing action filled (Confirmar), the correction tonal
  (Corregir), dismissing outlined in `negative` (Descartar); ≥ 48 dp. iOS keeps `.dincrPrimary` /
  `.dincrSecondary` and the system destructive button there.
- **Chips** (Android) are tonal (`surface-2`), without outline; the selected one uses the tint
  container **and a check icon**, so the selection never depends on color alone.
- **Secondary** (tint container): alternatives. **Text**: low-emphasis actions, cancel.
- **Destructive** (filled negative): only inside a confirmation; the first surface shows a text
  button in negative color.
- States: default, pressed (`tint-pressed`), disabled (40% opacity, no color change of label
  semantics), loading (label replaced by progress indicator, width kept, action blocked).

### Cards / Containers

- Inset grouped lists (iOS) / list items in a surface container (Android) for any list of records.
- Cards only for a self-contained summary (the key figure, a goal, a debt). Never nest cards.

### Inputs / Fields

- Visible label above the field, never placeholder-only. Border `field-border` (1 pt), 2 pt
  `tint` when focused. Error text below the field in `negative` with icon; the field border turns
  `negative`. Forms with more than one error after submit also show an error summary at the top
  (linked to each field) and move accessibility focus to it.
- Amount fields: numeric keypad, currency symbol from profile, tabular digits, large (`title-1`).

### Chips

- Filter chips for list filters (all / income / expenses / debts). Single-select behaves like a
  segmented control on iOS.

### Navigation

- iOS: `TabView` with five sections (Hoy, Movimientos, Plan, DINCR, Perfil), `NavigationStack` per
  tab, sheets for create/edit, large titles.
- Android: `NavigationBar` (compact) / `NavigationRail` (expanded) with the same five
  destinations, top app bar per screen, predictive back, modal bottom sheets for create/edit.

### Messages

Every message that means something is a `DincrMessage` with one of four kinds. The kind is
recognisable before reading (icon, color, shape) and is read first by VoiceOver/TalkBack.

| Kind | Means | Look | Never used for |
|------|-------|------|----------------|
| Technical error | something in DINCR failed or is degraded: network, service, paused changes, a mail connection to redo | neutral `surface-2`, cloud icon, `text-2` | a financial situation |
| Attention | a financial situation worth attention | `warning-container`, bell icon, leading `warning` accent bar | a failure of DINCR, promotions |
| Opportunity | something DINCR found that could help | `tint-container`, sparkles icon in `tint` | a problem, blocking or warning the user |
| Positive | progress, an improvement, a milestone | `positive-container`, seal icon | hiding a problem |

- Financial alerts get their kind only from their backend severity, through `MessageKind.financial`:
  `success` → positive; every other severity, including unknown ones → attention. A problem is
  never downplayed to a suggestion, and a financial alert is never a technical error.
  Opportunity is set explicitly by the screen that offers a recommendation.
- Global or connection problems (service slow or interrupted, changes paused, a mail connection
  that failed) use the technical-error look. The user declining a permission or a plan gate is a
  neutral notice.
- `ErrorState` (inline errors that mix invalid input and failed requests) keeps the `negative`
  look until each use is classified.
- `StatusBanner` is only for neutral notices (demo mode, a new version, a promotion, an action's
  result); it has no warning or error tone.

### Money row (signature component)

Leading category icon (`icon.md`) in a 40 pt `surface-2` circle; primary text (description) and caption (date ·
category); trailing amount in tabular `body` weight 600 with sign (`+` in `positive`, `−` in
`text`). Read-only rows show a lock caption, never a disabled look. Swipe actions (edit, delete)
are shortcuts only: the same actions are always reachable from the row's detail screen or context
menu, so no action is swipe-only.

## Owner identity (DINCR Owner / JARVIS)

The single Owner account is not a plan, so "plans don't repaint the app" does not apply to it. The
Owner keeps DINCR's structure, navigation (the same five tabs), system type, components and voice,
and changes only the scene, below a root that reads the server role (`dincrOwnerAppearance`):

- A deep petrol background (a quiet radial to near black in dark; white to pale blue in light; one
  flat color with Increase Contrast), blue-tinted surfaces with a hairline border (decorative only),
  and one cyan accent instead of the teal tint. Owner tokens: `OwnerColor` in DincrDesign
  (`Owner/OwnerTheme.swift`), light and dark, text ≥ 4.5:1 on every Owner surface.
- JARVIS has one quiet mark (a static cyan orb), never animated, glowing or game-like.
- Cards: radius 22; controls and quick actions: 18. Lists of records stay native lists or one
  grouped surface with separated rows — never one card per record.
- Everything else in this file still applies: no eyebrows, no stat-tile grids, money signed with
  `+` / `−` and never by color alone, unknown values "—", system materials only for blur.

## Personal appearance (APP-1, Owner-only experiment)

A person may choose a limited, validated set of alternatives to the base above. Phase 1 offers it
to the single Owner only (server gate `require_owner()` on `/user-product/appearance`); Free, Basic
and VIP always draw the **classic** set, which is this file exactly. The alternatives live in
[`jarvis-personal/native/design-tokens/appearance.json`](jarvis-personal/native/design-tokens/appearance.json),
next to this file's generator, which turns them into Swift and Kotlin and refuses any combination
that breaks the rules of this file.

| Option | Values (default for the Owner first) | Classic |
|--------|----------------------------------------|---------|
| Theme | Automático, Claro, Oscuro | the device setting |
| Palette (neutrals) | Océano, Clásico, Arena, Grafito | Clásico |
| Accent (the one tint) | Cian, Verde azulado, Ciruela, Tinta | Verde azulado |
| Text size (× the system scale) | Estándar 100 %, Pequeño 90 %, Grande 115 %, Muy grande 130 % | Estándar |
| Typeface | Sistema, Editorial (serif screen and section titles) | Sistema |
| Density | Cómoda, Compacta (12 gaps, 48 rows) | Cómoda |
| Surfaces | Con contorno (hairline, cards 22 / controls 16), Tonal | Tonal |

- **Océano + Cian + Con contorno is the Owner identity** (above), so the Owner's default is the
  same scene on iOS and Android; the generator test holds the tokens equal to `OwnerColor`.
- Every palette × accent × scheme keeps text ≥ 4.5:1 on `bg`, `surface` and `surface-2`, control
  boundaries and focus ≥ 3:1, labels on filled and tonal accents ≥ 4.5:1, status colors ≥ 4.5:1 and
  chart series ≥ 3:1 (`contrastFailures`, generate.test.mjs).
- Status, message and chart colors never change with the appearance: positive, negative, warning,
  info and VIP keep their meaning (Océano only uses the Owner identity's brighter positive in dark).
- The text size multiplies the platform scale (Dynamic Type / font scale); it never replaces it,
  and compact density never takes touch targets below 48.
- No new accent may collide with a status or chart meaning (no green, red, amber or indigo tint).
- Preferences belong to one account (`user_preferences`, one key per account in its workspace) and
  follow it to every signed-in device; a GET never writes and no stored value means the default.

## Do's and Don'ts

### Do:

- Show "—" or "Sin dato" when a value is unknown; never 0.
- Put the recovery action next to every error.
- Use platform controls (switches, pickers, sheets, alerts, snackbars) as they are.
- Confirm destructive actions with the object's name and the consequence.
- Keep every figure readable by VoiceOver/TalkBack as a full sentence ("Gastos: ciento veinte mil
  colones").

### Don't:

- No gradients behind content, no glass cards, no glow.
- No red for ordinary expenses; no green for "income" labels that are not events.
- No uppercase eyebrow kickers; no section numbers.
- No progress rings or decorative charts; every chart answers a question. A sparkline only sits
  next to the figure it summarizes, never alone (Data visualization).
- No custom navigation, custom back gestures or web-shaped controls.
- No per-plan color themes.
