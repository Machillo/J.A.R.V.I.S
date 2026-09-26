# DINCR 2.0 — behavioral design specification

Version **2.0.0**. Tokens (color, type, radius, spacing, component tokens) are normative in
[`/DESIGN.md`](../../DESIGN.md). This document specifies behavior: platform mapping, states,
feedback, motion, haptics, accessibility, charts, copy. Product truth is in
[`/PRODUCT.md`](../../PRODUCT.md). Reviews and decisions: [`DESIGN_REVIEWS.md`](DESIGN_REVIEWS.md).

Versioning: semantic. **Major** = a token is removed or renamed, or a rule changes meaning;
**minor** = a token or component is added; **patch** = a value is tuned within its role (contrast
re-validated). Every change updates the change log at the end and passes
`npm run test:design-tokens` (contrast gate).

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
| Size classes | iPhone: tab bar; iPad: `TabView` with `.sidebarAdaptable` style, readable width 600 pt, two columns where a list has a detail | `NavigationSuiteScaffold`: bar < 600 dp, rail ≥ 600 dp; list-detail pane ≥ 840 dp |
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
| Offline | Global banner "Sin conexión" (info); cached content readable; write actions follow the offline policy (parity B8) | |
| Degraded | Global banner (warning) "Algunas funciones pueden tardar" + "Ver estado" | |
| Writes paused (flag) | Global banner (warning) with server message; write buttons disabled with explanation on tap | |
| Feature unavailable (flag) | Full-screen empty-state variant with server message | |
| Partial data | Caption "Parcial" next to the figure + explanation sheet | §4.D of CLAUDE.md |
| Success | Sheet dismisses, list updates in place, brief confirmation (snackbar / status) | No celebratory modals |

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
| motion-instant | 100 ms | `.easeOut(duration: 0.1)` | `tween(100, easing = FastOutLinearInEasing)` | press feedback, toggles |
| motion-quick | 200 ms | `.snappy(duration: 0.2)` | `tween(200, easing = EmphasizedDecelerateEasing)` | content changes, chip selection, banner in/out |
| motion-standard | 300 ms | `.smooth(duration: 0.3)` | `tween(300, easing = EmphasizedEasing)` | list insert/remove, value changes on the key figure |
| navigation | system | system push / sheet | Material shared-axis X (nav), fade-through (tabs) | never custom |

Rules: motion conveys state change only; no entrance choreography on screen load; numbers may
count to a new value (≤ 300 ms) only when the value changes while visible. **Reduce Motion /
Remove animations**: replace movement with crossfade or instant change; no shimmer; no counting.

## 6. Haptics

| Event | iOS | Android |
|-------|-----|---------|
| Save succeeded | `.sensoryFeedback(.success)` | `HapticFeedbackConstants.CONFIRM` |
| Validation / server error | `.sensoryFeedback(.error)` | `HapticFeedbackConstants.REJECT` |
| Destructive confirmed | `.sensoryFeedback(.warning)` | `HapticFeedbackConstants.REJECT` |
| Segmented / chip selection | `.sensoryFeedback(.selection)` | `HapticFeedbackConstants.CLOCK_TICK` (only if system haptics enabled) |
| Unlock succeeded | none (system provides) | none |

Never on scroll, on navigation, or on data load. Respect system haptics settings.

## 7. Accessibility

- Contrast: all text ≥ 4.5:1, large text / icons / chart marks ≥ 3:1 — enforced by
  `npm run test:design-tokens` for token pairs.
- Increased contrast (iOS) / high-contrast text (Android): respected via platform APIs; borders
  become `line-strong`.
- Dynamic Type / font scale: every screen verified at the default, at XXL, and at the largest
  accessibility size (AX5 / 200%). Horizontal layouts stack; nothing truncates money.
- Screen readers: every money figure has a spoken label including sign and currency; rows combine
  into one element ("Supermercado, gasto, 12 de setiembre, menos quince mil colones"); decorative
  icons hidden; charts expose a summary and a data table alternative.
- Focus: logical order top-to-bottom; after a sheet closes focus returns to the invoking control;
  first invalid field receives focus on submit errors.
- Touch targets ≥ 44 pt / 48 dp.
- Never color alone: signs, icons, labels accompany status and series colors.
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
recessive (`line`), axis labels `caption` in `text-muted`. Interaction: tap/drag selection shows a
value callout; VoiceOver/TalkBack audio-graph or per-mark labels.

## 9. Platform baselines

| | iOS | Android |
|---|---|---|
| Minimum | **iOS 17** (Observation, `sensoryFeedback`, spring animations, `TabView` sidebar). Capacitor supports iOS 15, so this drops iOS 15–16 devices — **needs product-owner confirmation** | **minSdk 24** (parity with Capacitor), target/compile 36 |
| UI toolkit | SwiftUI; UIKit only where SwiftUI lacks an API | Jetpack Compose, Material 3 |

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

- Header shows the plan as a quiet badge (VIP uses `plan-badge-vip`; Free and Basic use a neutral
  badge). No per-plan palettes, no per-plan titles.
- Gated destinations are hidden, not disabled, unless the flag system reports temporary
  unavailability (then shown with the server message).

## 12. Web landing (dincr.com)

The landing is a *Persuade* surface on the web. It consumes the same color tokens (CSS custom
properties generated from DESIGN.md) so the site and the app read as one product; its layout,
typography scale and motion are specified in the landing's own surface brief (phase C3).

## Change log

| Version | Change |
|---------|--------|
| 2.0.0 | DINCR 2.0: unified palette (app + landing), single tint, calm money semantics, native platform mapping, states, motion, haptics, a11y, charts. Replaces the Capacitor-era per-plan palettes and glow/glass styling. |
