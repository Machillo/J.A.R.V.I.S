# DINCR 2.0 — behavioral design specification

Version **2.0.0**.

## 0. Source of truth

| Document | Role | Wins on |
|----------|------|---------|
| [`/DESIGN.md`](../../DESIGN.md) frontmatter | **Normative tokens**: color (light + `dark-`), typography roles, radius, icon size, spacing, component tokens. The only file generators and the contrast gate read. | Any token name or value |
| `docs/design/DESIGN_SYSTEM.md` (this file) | **Rules and platform mapping**: states, feedback, motion, haptics, accessibility, charts, numbers, forms, navigation, touch targets, and the behavioral values defined only here (motion durations, opacities, target sizes). It names tokens and never restates their hex values. | Behavior and platform mapping |
| [`/PRODUCT.md`](../../PRODUCT.md) | **Context / product truth**. Items marked *inferred* or *open* are not binding until the product owner confirms them. | Nothing visual; it motivates the rules |
| [`DESIGN_REVIEWS.md`](DESIGN_REVIEWS.md) | **Evidence ledger**: reviews, findings, decisions, disagreements. | Nothing; it records why |

Conflict rule: if this file and the DESIGN.md frontmatter disagree on a value, the frontmatter is
right and this file is the bug. The prose of DESIGN.md summarizes; the detailed rule lives here.

## Versioning and native synchronization

Semantic versioning of the DESIGN.md `version`:

- **Major (breaking)**: a token is removed or renamed, changes role, or a rule changes meaning.
  Requires regenerating native tokens and updating every consumer (apps, landing), or a
  deprecation period, plus a review entry.
- **Minor (additive)**: a token, component or rule is added. A new color token needs both schemes
  and its contrast pairs (the gate fails on a color that no pair or exemption covers).
- **Patch**: a value is tuned within its role; the gate re-validates it.
- **Deprecation**: a replaced token stays for at least one minor version, marked
  `# deprecated: use <new>` in the frontmatter and in the change log; generated native code keeps
  an alias until the next major.
- **Native synchronization**: native token files are generated from DESIGN.md, never edited by
  hand, and CI checks they are current. Landing custom properties mirror the same values (§12). A
  PR that changes a token lists the native and landing updates it requires.

Every change updates the change log at the end and passes `npm run test:design-tokens`.

---

## 1. Brand principles → interface rules

| Principle (PRODUCT.md) | Interface rule |
|------------------------|----------------|
| Truth before comfort | Unknown values render "—" with an explanation affordance; partial data is labeled ("Parcial · 12 de 30 días"); estimates say "estimado". |
| One next step | Each screen has at most one primary button; the overview ends in one suggested action. |
| Calm over urgency | No red for normal spending, no badges for non-actionable information, no countdowns, no auto-playing motion. |
| The platform is the product | Native navigation, controls, sheets, alerts, pickers, symbols. |
| Plans add depth, not a different app | Same palette, structure and components on all plans; VIP marked by a badge and extra destinations. |

## 2. Platform mapping

| Concept | iOS (SwiftUI) | Android (Compose, Material 3) |
|---------|---------------|-------------------------------|
| Top-level nav | `TabView`, 5 tabs, SF Symbols | `NavigationBar` (compact) / `NavigationRail` (≥ 600 dp), Material Symbols (Rounded) |
| Hierarchy | `NavigationStack` per tab, large titles | `NavHost` per destination, `TopAppBar` (medium on top level) |
| Create / edit | `.sheet` with `NavigationStack`, Cancel / Save in toolbar, `.presentationDetents([.medium, .large])` | `ModalBottomSheet` (short forms) or full-screen dialog destination (long forms) |
| Confirm destructive | `.confirmationDialog` or `.alert` with `role: .destructive` | `AlertDialog` with error-colored confirm |
| Transient feedback | No toasts (not an iOS pattern): the result is visible in place (sheet dismisses, row appears/updates) plus success haptic; when nothing visible changes, an inline status row at the top of the list for 4 s, announced to VoiceOver | `Snackbar` (with Undo when available) |
| Pickers | `DatePicker`, `Picker(.menu)`, `.segmented` | `DatePickerDialog`, `ExposedDropdownMenu`, `SingleChoiceSegmentedButtonRow` |
| Toggles | `Toggle` | `Switch` |
| Pull to refresh | `.refreshable` | `PullToRefreshBox` |
| Search | `.searchable` | `SearchBar` / `DockedSearchBar` |
| Lists | `List` `.insetGrouped` | `LazyColumn` + `ListItem` on surface container |
| Back | Edge swipe + back button (never disabled except unsaved-changes guard) | System/predictive back (`BackHandler` only for unsaved-changes guard) |
| Icons | SF Symbols, `.symbolRenderingMode(.hierarchical)` | Material Symbols Rounded, 24 dp, weight 400 |
| Materials | System bar/sheet materials | Tonal surfaces only |
| Size classes | iPhone: tab bar; iPad: tab bar, readable width 600 pt, two columns (`NavigationSplitView`) where a list has a detail; `.tabViewStyle(.sidebarAdaptable)` only on iOS 18+ behind `#available`, never as the baseline | `NavigationSuiteScaffold`: bar < 600 dp, rail ≥ 600 dp; list-detail pane ≥ 840 dp |
| Orientation | iPhone and iPad: all orientations supported (parity with Capacitor) | All orientations; state survives configuration change |
| Keyboard | Fields scroll above the keyboard; toolbar Done on numeric keypads | `imePadding()`; IME action Next/Done |
| Theme | `preferredColorScheme` from setting (system / light / dark) | `DincrTheme(darkTheme = …)`; Dynamic Color **off** (brand tint must stay stable for money semantics) |

Icon mapping (initial set):

| Meaning | SF Symbol | Material Symbol |
|---------|-----------|-----------------|
| Hoy | `chart.bar.xaxis` | `bar_chart` |
| Movimientos | `list.bullet.rectangle` | `receipt_long` |
| Plan | `target` | `target` |
| DINCR (advisor) | `sparkle` | `auto_awesome` |
| Perfil | `person.crop.circle` | `account_circle` |
| Income | `arrow.down.left` | `south_west` |
| Expense | `arrow.up.right` | `north_east` |
| Debt | `creditcard` | `credit_card` |
| Goal | `flag` | `flag` |
| Savings | `banknote` | `savings` |
| Warning | `exclamationmark.triangle` | `warning` |
| Error | `xmark.octagon` | `error` |
| Success | `checkmark.circle` | `check_circle` |
| Info | `info.circle` | `info` |
| Lock / read-only | `lock` | `lock` |
| Mail | `envelope` | `mail` |

## 3. States (every data screen)

| State | Pattern | Notes |
|-------|---------|-------|
| Loading (first) | Skeleton of the real layout (key figure bar + 3–5 row placeholders), shimmer disabled under reduced motion | No centered spinners over content |
| Loading (refresh) | Platform pull-to-refresh indicator; content stays | |
| Empty | Icon + one-sentence explanation of what will appear + the primary action that fills it ("Agregá tu primer movimiento") | Empty ≠ zero: an empty list is not "₡0 spent" |
| Error (screen) | Inline error card at the top: what failed, "Reintentar", "Ayuda" (support with context); cached content stays visible below when available | Uses API error mapping; incident reference shown when reported |
| Error (field) | Message under the field, icon, field outline negative; focus moves to first invalid field on submit | |
| Offline | Global banner "Sin conexión" (info); cached content readable; write actions follow the offline policy (parity matrix row B8, decision pending) | |
| Degraded | Global banner (warning) "Algunas funciones pueden tardar" + "Ver estado" | |
| Writes paused (flag) | Global banner (warning) with server message; write buttons disabled with explanation on tap | |
| Feature unavailable (flag) | Full-screen empty-state variant with server message | |
| Partial data | Caption "Parcial" next to the figure + explanation sheet | §4.D of CLAUDE.md |
| Success | Sheet dismisses, list updates in place; a brief confirmation (snackbar / status row) only when nothing visible changed or Undo exists (§18) | No celebratory modals |

## 4. Feedback and destructive actions

- Every write shows progress on the triggering control (button loading state), blocks
  double-submit, and ends in success feedback or an inline error — never silence.
- Destructive confirmation copy: title names the action + object ("¿Eliminar «Tarjeta BAC»?"),
  body names the consequence ("Se eliminarán la deuda y sus pagos. No se puede deshacer."), buttons
  "Eliminar" (destructive) and "Cancelar".
- Account deletion uses a dedicated confirmation screen that lists what will be deleted, with a
  destructive button and a prominent "Conservar cuenta". No typed-word or long-press confirmation
  (both are accessibility barriers).
- Undo (Android snackbar) only where the backend supports restore; otherwise confirmation first.

## 5. Motion

| Token | Duration | iOS | Android | Use |
|-------|----------|-----|---------|-----|
| motion-instant | 100 ms | `.easeOut(duration: 0.1)` | `tween(100, easing = LinearOutSlowInEasing)` | press feedback, toggles |
| motion-quick | 200 ms | `.snappy(duration: 0.2)` | `tween(200, easing = EmphasizedDecelerateEasing)` | content changes, chip selection, banner in/out |
| motion-standard | 300 ms | `.smooth(duration: 0.3)` | `tween(300, easing = EmphasizedEasing)` | list insert/remove, value changes on the key figure |
| navigation | system | system push / sheet | Material shared-axis X (nav), fade-through (tabs) | never custom |

| motion-reduced | 150 ms | `.easeInOut(duration: 0.15)`, opacity only | `tween(150)`, alpha only | replaces every movement under Reduce Motion |

Rules: motion conveys state change only; no entrance choreography on screen load; numbers may
count to a new value (≤ 300 ms) only when the value changes while visible. Modal sheets, dialogs,
navigation push/pop and tab switches use the system transition. The skeleton pulse (≤ 1 s cycle,
opacity only) is the only looping motion and exists only while loading. **Reduce Motion /
Remove animations** (iOS `accessibilityReduceMotion`, Android animator duration scale 0):
replace movement with a `motion-reduced` crossfade or an instant change; no pulse; no counting.
Nothing essential depends on animation: every state is readable in its final frame.

## 6. Haptics

| Event | iOS | Android |
|-------|-----|---------|
| Save succeeded | `.sensoryFeedback(.success)` | `HapticFeedbackConstants.CONFIRM` |
| Validation / server error | `.sensoryFeedback(.error)` | `HapticFeedbackConstants.REJECT` |
| Destructive confirmed | `.sensoryFeedback(.warning)` | `HapticFeedbackConstants.REJECT` |
| Segmented / chip selection | `.sensoryFeedback(.selection)` | `HapticFeedbackConstants.CLOCK_TICK` (only if system haptics enabled) |
| Unlock succeeded | none (system provides) | none |

Never on scroll, on navigation, on data load, or for passive warnings (a banner appearing). At
most one haptic per user action. Respect system haptics settings. Android `CONFIRM` and `REJECT`
exist from API 30; on API 24–29 emit no haptic for them (the visual feedback carries the meaning)
instead of substituting an unrelated constant. Devices without haptic hardware ignore them.

## 7. Accessibility

- Contrast by element type (WCAG 2.2 AA), enforced by `npm run test:design-tokens` in light and
  dark:
  - text: primary, secondary, metadata, **placeholder (`text-muted`)**, links, navigation labels,
    status text, text on filled and tonal components, banners, badges: ≥ 4.5:1 (SC 1.4.3);
  - control boundaries (`field-border`), focus indicator (`focus-ring`), selected-state icons,
    chart marks: ≥ 3:1 against the adjacent color (SC 1.4.11);
  - chart series against each other: OKLab ΔE ≥ 15 (normal vision) and ≥ 8 (protan/deutan);
  - exempt: disabled controls (SC 1.4.3, inactive components) and decorative separators and
    overlays (`line`, `line-strong`, `scrim`). A disabled control is still identified by more
    than its opacity: it is announced as unavailable, and a tap explains why when the reason is
    not obvious.
- Pairing rules the gate relies on: text on status containers uses `text`, `text-2` or the
  status color; fields and outlined controls sit only on `bg` / `surface` / `surface-2`
  (`field-border` is not validated on tinted containers); `focus-ring` equals `tint`, so it is
  always drawn with the 2 pt offset gap that separates it from a filled tint button.
- Increased contrast (iOS "Increase Contrast") / high-contrast text (Android) map onto existing
  tokens, with no separate palette: separators `line` → `line-strong`, `text-muted` → `text-2`,
  `field-border` width 1 → 2 pt. iOS may express this through asset-catalog appearances or
  generated dynamic colors that read `accessibilityContrast`.
- Dynamic Type / font scale: every screen verified at the default, at XXL, and at the largest
  accessibility size (AX5 / 200%). Horizontal layouts stack; nothing truncates money.
- Screen readers: every money figure has a spoken label including sign and currency; rows combine
  into one element ("Supermercado, gasto, 12 de setiembre, menos quince mil colones"); decorative
  icons hidden; charts expose a summary and a data table alternative.
- Focus: logical order top-to-bottom; after a sheet closes focus returns to the invoking control;
  first invalid field receives focus on submit errors.
- Touch targets ≥ 44 pt / 48 dp.
- Never color alone: income vs expense (sign `+` / `−`, icon, and "ingreso" / "gasto" in the
  spoken label), success/error (icon + text), selected state (filled symbol or indicator shape +
  weight + the platform "selected" trait), plan (badge text), chart series (legend + direct
  labels + position), financial status (words such as "Vencido", "Parcial", "Sin dato").
- Language: content `lang` es-CR / en; numbers read in the user's language.
- Status changes that appear without user action (offline, degraded, queued changes recovered)
  are announced once as a complete phrase (`AccessibilityNotification.Announcement` /
  `LiveRegion.Polite`) without moving focus.
- Banners and the bottom bar never cover the focused control or the keyboard.

## 8. Charts

Follows the dataviz method (validated palette in DESIGN.md).

| Question | Form | Notes |
|----------|------|-------|
| Income vs expenses by month | Grouped bars, 2 series (income teal, expense indigo), 2 pt gap, 4 pt rounded data ends | Legend always; value labels on selection; table alternative |
| Where the money goes | Horizontal bars, single hue (`chart-expense`), sorted desc, direct value labels | No legend (title names it) |
| Budget use per category | Linear progress bar, tint; over-limit segment in `negative` with icon and "excedido" text | |
| Debt / patrimony projection | Line, 2 pt, baseline at 0, markers ≥ 8 pt on selection only | One axis only |
| Goal progress | Linear progress bar with "₡X de ₡Y" text | No rings |

Charts: Swift Charts (iOS), Compose Canvas components in the shared UI module (Android). Grid lines
recessive (`line`), axis labels `caption` in `text-muted`, values and legends in text tokens (never
in the series color). Interaction: tap/drag selection shows a value callout; the selected mark gets
a 2 pt `surface` ring and the other bars dim to 40%; VoiceOver/TalkBack audio-graph or per-mark
labels.

Chart semantics and color-vision safety:

- Expense series use `chart-expense` (indigo), never `negative`. `negative` appears in a chart only
  for a real problem (over budget), always with icon and text.
- A balance or projection below zero keeps its series color; the zero baseline is drawn and the
  value label carries the sign. Red never means "below zero".
- The validated categorical set is two series. A third series is not an improvised hue: it becomes
  a new token pair validated by the gate in both modes, or the chart uses small multiples, direct
  labels, or a dash/texture pattern as secondary encoding. Six series are never distinguished by
  color alone.
- Every chart with two or more series has a legend and a table alternative.

## 9. Platform baselines

| | iOS | Android |
|---|---|---|
| Minimum | **Proposed iOS 17 — PRODUCT DECISION REQUIRED** (analysis below). The design system does not depend on it: every rule here has an iOS 16 implementation. | **minSdk 24** (parity with the Capacitor app), target/compile SDK 36 |
| UI toolkit | SwiftUI; UIKit only where SwiftUI lacks an API | Jetpack Compose, Material 3 |

**iOS minimum — technical analysis (the decision belongs to the product owner).** The Capacitor
app targets iOS 15.0 today.

| | iOS 17 (proposed) | iOS 16 | iOS 15 |
|---|---|---|---|
| APIs gained | Observation (`@Observable`), `.sensoryFeedback`, `.snappy` / `.smooth` animations, two-value `onChange`, `UnevenRoundedRectangle`, `AccessibilityNotification.Announcement`, `ContentUnavailableView` | `NavigationStack` / `NavigationSplitView`, Swift Charts, `.presentationDetents`, `.scrollDismissesKeyboard` | `.refreshable`, `.searchable`, `.monospacedDigit`, `AttributedString` |
| Equivalent on the lower target | — | `ObservableObject` / `@Published`; `UINotificationFeedbackGenerator` / `UISelectionFeedbackGenerator`; `.spring` / `.easeOut`; one-value `onChange`; a custom `Shape`; `UIAccessibility.post(.announcement)` | as iOS 16, plus `NavigationView` (deprecated), a custom chart view instead of Swift Charts, sheet detents through a UIKit bridge |
| Compatibility cost | none | moderate: the state-observation model is an architectural choice and costly to swap later; everything else is local wrappers | high: navigation, charts and sheets need UIKit bridges or custom code that the design rules assume are native |
| Devices dropped vs today | the devices whose last iOS is 15 or 16 | the devices whose last iOS is 15 | none |

Not known from the repository: how many current users run iOS 15–16. `.sidebarAdaptable` (iPad
sidebar) needs iOS 18 under any of these options and is gated by `#available` (§2).

**Android baseline.** minSdk 24 matches the Capacitor app; target and compile SDK 36. What sets
the floor: Compose and Material 3 run from API 21, so they do not force a higher minimum. Version
-dependent behavior the design must degrade gracefully on: haptic `CONFIRM` / `REJECT` (API 30,
§6), predictive back animations (API 33+ opt-in; plain back below), per-app language picker
(API 33; in-app setting below). Biometrics: `androidx.biometric` `BiometricPrompt` works from API
23, but combining `BIOMETRIC_STRONG` with `DEVICE_CREDENTIAL` is unsupported on API 28–29 and
`DEVICE_CREDENTIAL` alone before API 30, so the passcode fallback on those levels is a separate
step (§20). Neither native prototype includes a biometric library yet.

## 10. Copy and voice

- Spanish (Costa Rica, voseo) primary; English secondary; both complete for every string.
- Buttons are verbs naming the result: "Guardar gasto", "Registrar pago", "Conectar correo".
- Errors: what happened + what to do. "No pudimos guardar el gasto. Revisá tu conexión e intentá de
  nuevo." Never raw codes; support reference when available.
- Currencies are shown by code and symbol ("CRC ₡"), never by flag emoji.
- Numbers: currency and grouping from the user's profile (`number_format`, `currency_placement`,
  `base_currency`); dates in the user's language ("12 de setiembre").
- No exclamation marks in errors; no blame; no financial advice language outside the advisory
  screens (which carry the disclaimer).

## 11. Plan identity

- Header shows the plan as a quiet badge with its name as text (VIP uses `plan-badge-vip`; Free
  and Basic use the neutral `chip` colors). No per-plan palettes, no per-plan titles; the plan is
  never identified by color alone.
- Owner is internal and not part of this public design system: no Owner tokens, components or
  styles are defined here or imported into the Users apps.
- Gated destinations are hidden, not disabled, unless the flag system reports temporary
  unavailability (then shown with the server message).

## 12. Web landing (dincr.com)

The landing is a *Persuade* surface on the web. It uses the same color values as DESIGN.md (CSS
custom properties for both schemes) so the site and the app read as one product. Today those
properties are **hand-mirrored, not generated**; a sync check (DESIGN.md frontmatter vs the
landing's custom properties) is required before the landing claims token parity, and property
names should follow token names. Its layout, type scale and motion are specified in the landing's
own surface brief (phase C3); any exception to the app rules (for example page-load entrance motion
or a blurred header) is written there, and `prefers-reduced-motion` always wins.

## 13. Typography rules (both platforms)

- The DESIGN.md sizes are the iOS default-size reference. Implementations use the platform text
  style (iOS `Font.TextStyle`, Android `MaterialTheme.typography` in `sp`), never a fixed size, so
  Dynamic Type and font scaling apply. Android keeps the M3 role sizes (for example
  `displaySmall` 36 sp for `display-amount`); matching iOS points exactly is not a goal.
- Semantic roles: display = `display-amount`; title / headline = `title-1`, `title-2`; body =
  `body`, `body-small`; label = `label`; caption = `caption`; numeric / financial emphasis =
  `display-amount` for the key figure and the row's role at weight 600 with tabular digits.
- No bundled fonts in the apps. Icons that accompany text scale with it (SF Symbols follow the
  text style; Android icons use `icon.*` in dp and grow with the row); illustrative empty-state
  icons are sized from a text style, not from a fixed number.
- At the largest sizes money wraps to its own line; it is never truncated or shrunk below the
  `body` size.

## 14. Touch targets and density

| Control | Visual size | Minimum hit target |
|---------|-------------|--------------------|
| Buttons (primary, secondary, destructive) | 52 height | full button |
| Text button | 44 height | 44 pt × 44 pt / 48 dp × 48 dp |
| Icon button | `icon.lg` (24) glyph | 44 pt / 48 dp square |
| Chip / filter chip | 36 height (Android M3 chip 32 dp is acceptable) | 44 pt / 48 dp (expanded, not visible) |
| Segmented control | platform height | platform control; the whole segment is tappable |
| Checkbox / radio / switch | platform control | the whole row toggles |
| Tab / navigation item | platform | platform |
| Candidate Accept / Reject / Own transfer | text buttons with labels, never icon-only | 44 pt / 48 dp each, ≥ 8 apart |
| Destructive action | text button (first surface) / filled button (confirmation) | as buttons, ≥ 8 from the nearest other action |

Density: layouts are built from spacing tokens and flexible widths, never fixed widths. They must
hold at 320 pt (small iPhone with Display Zoom) and 360 dp (compact Android) up to large phones;
side margin `spacing.4`. Pairs placed side by side stack when they do not fit. Tokens carry no
device-specific values, so tablet layouts (readable width 600, list-detail ≥ 840 dp) can be added
without new tokens.

## 15. Component states

`–` = not applicable. Disabled = 40% opacity of the whole control (content and container) on both
platforms, announced as unavailable; exempt from contrast (§7). Focused = `focus-ring` 2 pt with
2 pt offset (hardware keyboard / switch control), except text fields (2 pt `tint` border).

| Component | Pressed | Selected | Loading | Error | Success |
|-----------|---------|----------|---------|-------|---------|
| Button primary | `tint-pressed` (iOS); ripple over `tint` (Android) | – | label → progress, width kept, blocked | – (error shows at the form) | – |
| Button secondary / text / destructive | system highlight (iOS) / ripple (Android) | – | as primary | – | – |
| Icon button | system highlight / ripple | toggles use filled symbol + `tint` | progress in place | – | – |
| Input / select | – | – | submitting: read-only, value kept | border `negative`, icon + message below | – |
| Segmented currency selector | platform | platform selected segment (selection cue is shape, not only color) | – | – | – |
| Card | whole-card press only if it navigates | – | skeleton | inline error card | – |
| List row | system highlight / ripple | checkmark + trait (multi-select) | skeleton row | row caption with icon | row updates in place |
| Navigation item | platform | platform (filled symbol, indicator, "selected" trait) | – | – | – |
| Dialog / sheet | – | – | confirm button loading, dismiss blocked while writing | error inline inside, content kept | dismisses, result shown in place |
| Banner | action button states | – | – | `negative-container` + icon | `positive-container` + icon, informational |
| Snackbar (Android) / status row (iOS) | action button states | – | – | not used for errors that need action | confirmation, 4 s, announced |
| Candidate controls | as buttons | – | the pressed one loads, the others disable | inline under the candidate | candidate leaves the list, status row / snackbar |

## 16. Forms

- **Label** always visible above the field (`label` role, `text-2`); the placeholder is an
  example value only (`text-muted`) and never the label.
- **Helper** text below in `caption` / `text-2`; replaced by the error message while invalid.
- **Required / optional**: when most fields are required, mark the optional ones "(opcional)";
  otherwise mark required ones with the word, not an asterisk alone.
- **Error**: after submit or on blur, message below with icon, border `negative`; error summary
  at the top when there is more than one (DESIGN.md Inputs).
- **Numeric intent**: CRC amounts use a number pad without decimals; USD amounts and exchange
  rates use a decimal pad (iOS `.numberPad` / `.decimalPad`; Android `KeyboardType.Number` /
  `KeyboardType.Decimal`).
- **Currency**: the symbol of the entry's currency is a leading, non-editable adornment; when the
  entry can be in CRC or USD, a segmented selector sits next to the amount.
- **Exchange rate field**: shown only when the entry currency differs from the account base
  currency; label "Tipo de cambio (₡ por US$1)"; required; may be prefilled only with the user's
  own last rate (labelled as such), never with a fetched or invented one; the converted base
  amount is shown as a caption ("≈ ₡6.315").
- **Disabled** fields explain why when tapped; **submitting**: fields read-only, primary button
  loading, double submit blocked (§4).

## 17. Numeric presentation (display contract only — no conversion here)

| Case | Rule | Example (es-CR) |
|------|------|-----------------|
| Symbol | Narrow symbol of the amount's own currency; code added where currencies mix or are ambiguous | ₡15.000 · US$12,50 |
| Decimals | CRC 0; USD 2; stored values are not rounded for display elsewhere | ₡15.000 · $12,50 |
| Grouping / decimal separator | From the user's profile / language, never hard-coded | |
| Negative / outflow | U+2212 minus before the symbol, in `text` (not red) | −₡15.000 |
| Received money | `+` in `positive` only for a completed inflow | +₡250.000 |
| Zero | Known zero: no sign | ₡0 |
| Unknown | "—" or "Sin dato", never 0 | — |
| Large amounts | Full digits in rows and key figures; abbreviations only on chart axes, with the full value in the callout and spoken label | ₡1,2 M (axis only) |
| Percentages | Integer; one decimal only below 1 %; a non-zero value never shows "0 %" | 18 % · 0,4 % |
| Exchange rate | Always ₡ per US$1, as the user entered it | ₡505,25 por US$1 |
| Converted entry | Original amount first, base amount and rate as caption | US$12,50 · ≈ ₡6.315 · TC 505,25 |
| Masked amount (only if a privacy mode is introduced; none exists today) | Fixed-width mask, same for every amount, spoken "importe oculto" | ₡ •••• |
| Account numbers | Last four digits only | •••• 1234 |

Spoken labels include sign and currency words ("menos quince mil colones").

## 18. Feedback: which pattern when

| Situation | Pattern (both platforms) |
|-----------|--------------------------|
| A field is invalid | Inline error under the field (+ summary if more than one) |
| A screen could not load or save | Inline error card at the top of the screen with the recovery action |
| App-wide condition (offline, degraded, recovering, writes paused, mail needs reconnection, plan notice) | Banner at the top, persistent while true, with its action |
| A write succeeded and the change is visible | No extra message beyond the change itself (+ success haptic) |
| A write succeeded and nothing visible changed, or Undo is possible | Android `Snackbar`; iOS inline status row (§2), 4 s, announced |
| A decision is needed before continuing (destructive, irreversible, leaving unsaved changes) | Dialog / confirmation dialog |
| Waiting for a user-triggered action | Progress inside the triggering control |
| First load | Skeleton of the real layout |
| Refresh | Platform pull-to-refresh indicator |
| No data yet | Empty state with the action that fills it |

Errors are never shown as snackbars or status rows only; success is never a modal dialog.

## 19. Navigation

- Five top-level destinations (§2), each with its own stack; the selected tab uses the platform
  selected style. Plan-gated destinations are hidden (§11).
- **Back**: the platform back (edge swipe / system and predictive back) always returns to the
  previous screen of the same stack; it is intercepted only for unsaved changes.
- **Sheet vs modal**: create/edit forms open as sheets (iOS) / bottom sheets or full-screen
  dialog destinations (Android); confirmations are dialogs; full flows that replace the app
  (login, onboarding, app lock, forced update) are full-screen and not dismissible by swipe.
- **Deep-link destinations** (including OAuth returns): open the destination inside its tab stack
  so back works; if the session is locked or signed out, authenticate first and then continue to
  the destination; a gated or unknown destination shows the gate explanation or "no encontramos
  esa pantalla", never a blank screen; an OAuth return shows its result (connected / cancelled /
  failed with retry) on the screen that started it.
- **Badges**: only for something the user can act on (pending mail candidates, mail needs
  reconnection), as a count or dot with a spoken label. Service outages are shown as a state
  inside the destination, not as a tab badge.

## 20. Security and privacy UX

- **Sensitive values**: error, empty and loading states never show amounts, account numbers,
  email content, addresses or tokens; account numbers show the last four digits; with app lock
  on, the app-switcher snapshot shows a neutral cover without amounts.
- **Auth errors**: one generic message for wrong credentials (no hint whether the email exists),
  recovery action next to it; expired session → sign-in screen explaining the session ended.
- **Permission errors**: say what is unavailable and why in product terms (plan, feature
  unavailable), never internal ids or codes; include the support reference when one exists.
- **Mail permission loss**: warning banner "Tu correo necesita reconectarse" with "Reconectar";
  already-reviewed data stays; nothing from the email content is shown in the banner.
- **Account deletion**: dedicated screen (§4) listing what is deleted; after confirmation, a
  final screen with no residual data.
- **Biometric failure / app lock**: message inline under the lock control (not a dialog), with
  "Intentar de nuevo" and the device-passcode fallback; lockout says to use the passcode or wait;
  not enrolled explains how to enable it or turn app lock off; the content behind the lock is
  never rendered until unlocked.

## 21. Native platform identity

| Shared across iOS and Android | Native to each platform |
|-------------------------------|-------------------------|
| Tokens (color, type roles, radius, spacing, icon sizes) and their semantics | Navigation containers, transitions and back behavior |
| Money presentation (§17) and copy (§10) | Controls: switches, pickers, segmented controls, sheets, dialogs, snackbar vs status row |
| States, feedback choice (§18) and destructive rules (§4) | Icon set (SF Symbols / Material Symbols) and type ramp sizes |
| Accessibility rules and chart semantics | Haptic APIs, press feedback (highlight / ripple), large title vs top app bar |

Android does not copy iOS layouts and iOS does not copy Material components; the same task
reads as the same product through tokens, content and hierarchy.

## Change log

| Version | Change |
|---------|--------|
| 2.0.0 | DINCR 2.0: unified palette (app + landing), single tint, calm money semantics, native platform mapping, states, motion, haptics, a11y, charts. Replaces the Capacitor-era per-plan palettes and glow/glass styling. |
| 2.0.0 (final audit, pre-release) | No token name or value changed. Added: source-of-truth hierarchy, versioning and native sync, typography, touch targets, component states, forms, numeric presentation, feedback, navigation, security/privacy UX, platform identity, iOS/Android baseline analysis. Fixed: iPad sidebar needs iOS 18, Android `motion-instant` easing, API-level haptic fallbacks, landing tokens are mirrored not generated. Contrast gate now covers pairwise chart distinction, status-container supporting text, token coverage and CRLF checkouts. |
