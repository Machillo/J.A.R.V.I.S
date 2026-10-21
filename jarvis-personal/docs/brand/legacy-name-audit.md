# Legacy product name audit

The product is **DINCR**, written exactly like that. FINVA is a historical internal name. This
document inventories every remaining occurrence of the legacy name (`FINVA`, `Finva`, `finva`) on
`main` as of 2026-10-21 (base `15edcd0d`), classifies it, and says why it stays or how it can move.

Guard: `npm run test:brand` (`frontend/scripts/test-brand-name.mjs`, in CI) fails when the legacy
name reaches a string the native apps can show, a localized resource, the store copy or the
landing. The web app's copy is guarded by `test-i18n.mjs` (`INTERNAL_PERSONA`). Both guards catch
any case of the name; comments are history and are not copy.

## Summary

| Group | Occurrences | Result |
|---|---|---|
| A. Visible to the user (screens, menus, messages, sign-in, settings, notifications, mail, store and landing copy) | **0** | Nothing to correct. Verified per client below and pinned by the guards. |
| B. Product identity and metadata (app name, display name, bundle/package, site title, manifests, store texts) | **0** | Every surface already says DINCR. |
| C. Technical identifiers and history | ~3000 in 277 files | Kept for compatibility, classified below. One of them (C7) can leak outside the app and has a staged plan. |

Counts come from `git grep -i finva` with a context classifier; a line can hold several matches.

## A. Visible to the user — verified clean

| Surface | Where checked | Result |
|---|---|---|
| Native Android app (Kotlin) | every string literal in `native/android/**/src/main`, comments excluded | only the allow-listed technical literals of C7 and C9 |
| Native iOS app (Swift, `.strings`) | every string literal in `native/ios` (non-test), localized resources | same |
| Capacitor app (React) | `test-i18n.mjs` AST walk of every visible attribute and copy call | no legacy name; i18n keys such as `nav.finvaOperations` render "Operaciones DINCR" / "DINCR operations" |
| Store copy | `store-assets/copy/*.json` | clean |
| dincr.com | `frontend/landing` sources and the built `landing-dist` | clean |
| Backend messages to users | `HTTPException` details and notification copy | clean. The only detail naming a FINVA variable (`FINVA_GMAIL_CRON_SECRET no está configurado.`) answers the maintenance cron, never an app user. |

## B. Product identity and metadata — verified

| Item | Value |
|---|---|
| Android app name (Capacitor `strings.xml`, native manifest `android:label`) | DINCR |
| iOS display name (Capacitor `Info.plist`, native `Base.xcconfig`) | DINCR |
| Bundle / application id (all apps) | `com.dincr.app` |
| Capacitor `appName`, web `<title>` | DINCR |
| Landing title, `og:site_name` | DINCR |

## C. Technical identifiers that stay

| Class | Count | Files | Examples | Why it stays | Safe to rename? |
|---|---|---|---|---|---|
| C1 CSS classes | 1357 | 50 | `.finva-card`, `finva-theme.css` | Selectors of the Capacitor app; protected by `test-visual-freeze.mjs`. Never shown. | Yes, mechanically, in a dedicated rename PR together with the visual-freeze baseline. |
| C2 code identifiers | 140 | 42 | `FinvaOnboarding`, `FinvaFormSheet`, `FinvaApiError` | Component and class names. Never shown. | Yes, in the same dedicated rename PR (no behavior change). |
| C3 storage keys and DOM events | 291 | 15 | `finva:app-lock:<id>`, `finva:api-error` | Keys already stored on users' devices (app lock, first-run, operation queue). Renaming without a migration resets app lock and loses queued offline operations. | Only with a read-old/write-new migration in the client; events can be renamed freely with their listeners. |
| C4 database | 510 | 70 | `finva_gmail_connections`, `finva_email_candidates`, `transactions.source = 'finva'` | Production tables, columns and stored values; RLS, functions and history depend on them. | No as part of this cleanup. A rename is a production migration (human gate, `migration-gate-acknowledged`). |
| C5 env vars, secrets, headers | 29 | 8 | `FINVA_GMAIL_CLIENT_ID`, `X-Finva-Cron-Secret` | Names configured in Render and GitHub secrets. | Only by accepting both names first, then changing production config (human gate). The Microsoft mail settings already accept a DINCR name. |
| C6 paths and modules | 64 | 18 | `src/products/finva/` | Folder of the public app's modules. | Yes, in the dedicated rename PR. |
| C7 mail OAuth return scheme | 23 | 11 | `com.finva.app://gmail/callback` | **The one that can leak outside the code**: the backend sends this URL to the browser after Gmail/Outlook consent. Every app claims it so the return reaches DINCR. | Staged plan below; needs production configuration (human gate). |
| C8 store product ids | 6 | 1 | `finva.vip.monthly` (backend defaults) | Defaults overridden by environment variables; store product ids are fixed once created and are not shown to users (the stores show the product's title). | Decide the final ids before the products are created in the consoles (`native/RELEASE_IDENTITY.md` step 3); then change the defaults. |
| C9 API enum value | 7 | 5 | `method: "finva"` in the VIP debt plan | API contract value; no client renders it. | Yes with a versioned contract change; no visible gain. |
| C10 analytics screen names | 2 | 1 | `trackScreen("finva_<page>")` | PostHog dashboards and history are keyed by these names. | Only with a dashboard migration; internal only. |
| C12 docs, skills, history | 93 | 22 | `CLAUDE.md`, audits, release notes | Describe historical names and migrations. | Kept; CLAUDE.md now states that FINVA is never used as the product name. |
| C13 tests, guards, labs | 478 | 95 | fixtures, guards that assert the name is absent | Test the identifiers above, or forbid the legacy name. | Follow their identifiers. |

## C7 — staged plan for the mail return scheme (prepared, not executed)

Today every client claims `com.finva.app://gmail/callback` and the backend default is that URL
(`gmail_service.py`, `microsoft_mail.py`, `FINVA_GMAIL_RETURN_URL`). The Capacitor Android and iOS
apps and the native Android app also claim `com.dincr.app://gmail/callback`. The native iOS app's
`ASWebAuthenticationSession` waits for one scheme (`AppModel.mailCallbackScheme = "com.finva.app"`).

1. Release the native iOS app with `mailCallbackScheme` matching the backend setting (it already
   claims both schemes).
2. Confirm that the minimum supported version of every installed client claims
   `com.dincr.app://gmail/callback` (release policy / kill switch).
3. **HUMAN GATE (production configuration):** set `FINVA_GMAIL_RETURN_URL` in Render to
   `com.dincr.app://gmail/callback`. No code change needed; changing the code default alone would
   not move production if the variable is set, and would break clients that predate step 2.
4. After one release cycle, remove the legacy `com.finva.app` claims (Capacitor manifest and
   Info.plist, native `AppModel`), the allow-listed literal in `test-brand-name.mjs`, and change
   the code default.

## Optional follow-up: internal rename (C1, C2, C6)

Renaming components, classes and the `products/finva` folder to DINCR names is safe for users but
touches ~120 files that other work edits daily, so it belongs in its own PR, run when no other
branch is open on the Capacitor app. Storage keys (C3) need a client migration; database (C4),
environment (C5) and analytics (C10) renames need production gates and are not part of it.
