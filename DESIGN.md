---
name: DINCR 2.0
description: Calm, trustworthy personal finance for iOS and Android — one identity, native on each platform.
version: 2.0.0
colors:
  # Light scheme
  bg: "#F5F7FA"
  surface: "#FFFFFF"
  surface-2: "#EDF1F6"
  line: "#DCE3EC"
  line-strong: "#C3CEDC"
  field-border: "#7A889E"
  focus-ring: "#0B6E68"
  scrim: "#0B1526"
  text: "#0B1526"
  text-2: "#46546A"
  text-muted: "#5B6980"
  tint: "#0B6E68"
  tint-pressed: "#085B56"
  tint-container: "#D5F0EC"
  on-tint: "#FFFFFF"
  on-tint-container: "#053B37"
  positive: "#08734F"
  positive-container: "#D8F3E6"
  negative: "#B4233F"
  negative-container: "#FBE0E5"
  warning: "#9A5800"
  warning-container: "#FCEBCF"
  info: "#0B5C8E"
  info-container: "#DDEEFA"
  vip: "#8A5A00"
  vip-container: "#F7EBCF"
  chart-income: "#008C7A"
  chart-expense: "#5B63C9"
  # Dark scheme
  dark-bg: "#0A1220"
  dark-surface: "#111B2C"
  dark-surface-2: "#182438"
  dark-line: "#24324A"
  dark-line-strong: "#34445F"
  dark-field-border: "#65758F"
  dark-focus-ring: "#3CCFBF"
  dark-scrim: "#000000"
  dark-text: "#EEF3F9"
  dark-text-2: "#B3C0D2"
  dark-text-muted: "#93A2B8"
  dark-tint: "#3CCFBF"
  dark-tint-pressed: "#2DB5A6"
  dark-tint-container: "#0E3A38"
  dark-on-tint: "#04201D"
  dark-on-tint-container: "#BFF2EB"
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
  banner-warning:
    backgroundColor: "{colors.warning-container}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  banner-error:
    backgroundColor: "{colors.negative-container}"
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

# Design System: DINCR 2.0

Normative tokens are in the frontmatter above. The full behavioral specification (motion, haptics,
states, accessibility, charts, platform mapping, copy) is in
[`docs/design/DESIGN_SYSTEM.md`](docs/design/DESIGN_SYSTEM.md); independent reviews are in
[`docs/design/DESIGN_REVIEWS.md`](docs/design/DESIGN_REVIEWS.md).

## Overview

DINCR 2.0 is a **Restrained**, content-first system for an *Operate* product: people check what they
have, record what happened and decide the next step. Physical scene: a phone in one hand, on a bus
at 7 a.m. or on the couch at 10 p.m. — so light and dark are both first-class and **follow the
system setting by default**, with an in-app override.

The identity lives in three places and nowhere else: a single deep-teal **tint** (actions, current
selection, focus), **tabular money figures** set large and calm, and a **voice** that states money
facts plainly. Everything else is the platform: SwiftUI and Material 3 components, system type,
system navigation. The previous generation's glow gradients, glass cards and per-plan re-skins are
retired.

## Colors

### Primary

- **Tint** (`tint` / `dark-tint`): the only interactive color. Primary buttons, links, selected
  tabs and chips, focus rings, progress toward a user goal. Never decoration, never a background
  wash.
- **Tint container**: tonal secondary actions and selected chips.

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
- Native implementation: every color is a named asset (iOS asset catalog with Any, Dark and
  Increased Contrast appearances; Android `ColorScheme` roles for light and dark). No raw hex in
  screen code.

### Semantic (status)

| Role | Meaning | Never used for |
|------|---------|----------------|
| positive | received money, goal reached, success confirmation | decoration, "income" labels that are not a completed event |
| negative | error, overspent budget, overdue payment, destructive action | ordinary expenses |
| warning | needs attention soon (missing data, payment in ≤ 3 days, needs reconnection) | promotions |
| info | neutral system notices, service status | brand accents |
| vip | the VIP plan badge only | anything else |

Status colors always ship with an icon and text. Money is signed with `+` / `−` — never by color
alone.

### Data visualization

`chart-income` (teal) and `chart-expense` (indigo) are the two series colors. Validated with the
dataviz six-checks validator in both modes (lightness band, chroma floor, CVD ΔE ≥ 13.7 deutan,
normal-vision ΔE ≥ 19, ≥ 3:1 on surface). Single-series magnitude charts use `chart-expense` alone.

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

- Depth is **tonal**: `bg` < `surface` < `surface-2`. Cards and lists do not cast shadows.
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
| full | 999 | chips, badges, avatar |

iOS uses continuous ("squircle") corners. No progress rings; progress is a linear bar with its value
in text.

## Components

### Buttons

- **Primary** (filled tint): one per screen or sheet; the action that completes the task.
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

### Money row (signature component)

Leading category icon (`icon.md`) in a 40 pt `surface-2` circle; primary text (description) and caption (date ·
category); trailing amount in tabular `body` weight 600 with sign (`+` in `positive`, `−` in
`text`). Read-only rows show a lock caption, never a disabled look. Swipe actions (edit, delete)
are shortcuts only: the same actions are always reachable from the row's detail screen or context
menu, so no action is swipe-only.

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
- No progress rings, sparklines or decorative charts; every chart answers a question.
- No custom navigation, custom back gestures or web-shaped controls.
- No per-plan color themes.
