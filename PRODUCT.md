# Product

<!-- impeccable:product-schema 1 -->

> Source: derived from the repository (`CLAUDE.md`, the Capacitor app, the native parity audit)
> and the design + native migration brief. Facts marked *(inferred)* were not confirmed in an
> interview and must be confirmed by the product owner before being treated as binding. The
> classification of every claim is in "Fact status" at the end.

## Platform

adaptive

The app ships natively on iOS (Swift + SwiftUI) and Android (Kotlin + Jetpack Compose) with one
DINCR identity expressed through each platform's conventions. The public website `dincr.com`
(`jarvis-personal/frontend/landing`) is a separate **web** surface: marketing, legal and support
only, never a second financial app.

## Users

People in Costa Rica managing their personal money from their phone: income that arrives by salary
or by the hour, everyday expenses, credit cards and loans, savings goals and an emergency fund.
Typical sessions are short check-ins ("how much do I have left this month?", "did that payment go
through?") plus occasional planning sessions (budget, debt strategy, goals). *(inferred: usage
rhythm)*

Plans: **Free** (record and understand), **Basic** (organize: budget, calendar, recurring, reports,
strategy), **VIP** (direction: projections, scenarios, mail automation, monthly review). **Owner** is
internal and out of scope for the public apps.

## Product Purpose

DINCR helps a person understand their current financial situation and choose the next concrete
step: organize, plan, move forward, achieve more. Success is a user who knows what is truly
available this month, what they owe, and what to do next, without being misled by partial data.

## Positioning

- Deterministic, explainable guidance built from the user's own data; **no generative AI at
  runtime**, and mail or bank content is never sent to an AI provider.
- **Declared vs. discovered data are kept distinct**: unknown is never shown as zero, and partial
  imported evidence never silently replaces what the user declared.
- Built for Costa Rican realities: colones and dollars, aguinaldo, local banks, voseo Spanish.

## Operating Context

- Primary: phone, one hand, often on the go; dark and light environments. *(inferred)*
- Mail automation (VIP) reads bank notification emails read-only after explicit consent; results
  are reviewed (accept / reject / own transfer) before affecting totals.
- Offline and degraded-service states exist and are communicated (queued changes, health banner).
- App lock with device biometrics or passcode.

## Capabilities and Constraints

- Business logic lives in the FastAPI backend; native clients present, navigate and integrate with
  the platform. They do not re-implement financial calculations (see
  `docs/native/CURRENT_STATE_AUDIT.md` §5, added by the native parity audit; not on `main` until
  that audit merges).
- Full feature inventory: `docs/native/PARITY_MATRIX.md` (same parity audit).
- Languages: Spanish (Costa Rican voseo) primary, English secondary.
- Currency display depends on the multi-currency contract in progress (CRC/USD). **Open decision.**
- Store billing is not live; paid plans are free during the current promotion.

## Brand Commitments

- Name: **DINCR** (all caps). Tagline in product: "Tu dinero, con propósito".
- Voice: warm, direct, second-person voseo ("Registrá", "Podés"), never alarmist; money problems
  are stated plainly with the recovery step.
- Positioning words from the brief: modern, calm, financial, trustworthy; avoid gimmicky
  "fintech neon".
- Existing mark: the letter "D" monogram used in login and setup. *(no vector master in the repo —
  open item)*

## Evidence on Hand

- Bank logos for supported institutions: `jarvis-personal/frontend/src/assets/institutions/`.
- Legal documents are linked from dincr.com (terms, privacy).
- No testimonials, user counts, press or security certifications exist in the repository; none may
  be fabricated on any surface.

## Product Principles

1. **Truth before comfort.** Show what is known, mark what is unknown, never invent a number.
2. **One next step.** Every screen answers "what should I do now?" before offering more.
3. **Calm over urgency.** Money is stressful; the interface lowers the temperature. Red means a
   real problem, not "an expense happened".
4. **The platform is the product.** A fluent iPhone or Android user should trust DINCR immediately.
5. **Plans add depth, not a different app.** Free, Basic and VIP share one identity and structure.

## Accessibility & Inclusion

- WCAG 2.2 AA contrast for all text; information never conveyed by color alone (signs, icons, labels).
- Dynamic Type (iOS) and font scaling (Android) up to the largest accessibility sizes without
  losing content.
- VoiceOver and TalkBack reading order and labels for every control and every money figure.
- Reduced motion respected on every platform.

## Fact status

**Confirmed from code** (Capacitor app on `main`): plans Free / Basic / VIP and the internal
Owner; tagline "Tu dinero, con propósito" (login screen); the "D" monogram (a text glyph; no vector
master); bank logos in `src/assets/institutions/`; app lock with device biometrics or passcode;
offline queue and health banners (offline, recovering, degraded); mail review with accept / reject
/ own transfer; store billing disabled by feature flag; voseo copy; CRC and USD as the supported
currencies; Capacitor targets iOS 15.0 and Android minSdk 24 / target 36.

**Confirmed from product requirements** (`CLAUDE.md`): DINCR is a mobile product and dincr.com is
marketing, legal and support only; Owner is internal and never purchasable; no generative AI at
runtime and mail/bank content never reaches an AI provider; declared vs discovered data and
unknown ≠ zero; business logic in the backend.

**Inferred — owner confirmation required:**

1. Usage rhythm (short check-ins plus occasional planning sessions).
2. Operating context (phone in one hand, on the go, light and dark environments).
3. Audience description (people in Costa Rica with salary or hourly income); supported by the
   aguinaldo and local-bank features, not stated as a requirement.
4. Native apps in Swift + SwiftUI and Kotlin + Compose (the migration brief; `main` ships
   Capacitor).
5. The exact per-plan feature list: in code, some Basic capabilities are gated by feature flags
   or in the backend rather than by plan, and strategy is available to Free.
6. Paid plans being free during the current promotion (the client shows a promotion; the price
   comes from the backend catalog).
7. English as a complete secondary language (the code has es/en strings).
8. Positioning words (modern, calm, financial, trustworthy) from the brief.
9. Multi-currency display (open decision) and the vector master of the "D" mark (open item).
10. iOS minimum version (proposed 17; see `docs/design/DESIGN_SYSTEM.md` §9 — product decision).
