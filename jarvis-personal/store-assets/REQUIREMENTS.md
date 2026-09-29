# App Store / Google Play screenshot requirements (audit)

Read from the official pages on **2026-09-29**. Re-read them before every submission and update
`config/targets.json` if anything changed. Nothing here was uploaded to either store.

Sources:
- Apple, *Screenshot specifications*: https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications/
- Google, *Add preview assets to showcase your app*: https://support.google.com/googleplay/android-developer/answer/9866151
- Google, *Store listing asset policy (screenshots)*: https://support.google.com/googleplay/android-developer/answer/1078870

## App Store Connect

| Item | Requirement | DINCR decision |
|---|---|---|
| iPhone | **6.9"** portrait 1260×2736, 1290×2796 or **1320×2868** is required when the app runs on iPhone. 6.5", 6.3", 6.1", 5.5" and 4.7" are scaled down from it when not supplied | `apple-iphone-69` at **1320×2868** |
| iPad | **13"** portrait 2064×2752 or 2048×2732 is **required if the app runs on iPad**. 11", 12.9", 10.5" and 9.7" are scaled from it | `apple-ipad-13` at **2064×2752** (see iPad note) |
| Format | `.png`, `.jpg` or `.jpeg`; **no alpha channel or transparency** | Opaque 24-bit PNG (RGB, no tRNS), enforced by `png.mjs` and `validate.mjs` |
| Count | 1 to 10 per localization | 3 screens: what the native iOS app has today (overview, transactions, Plan) |
| Device frames | Allowed | Generic rounded frame, no real device model or trademark |
| Paid features | Content shown that needs a purchase must say so (App Review 2.3.2) | Every screen carries its plan's badge (`screens.json` `plan`, checked by `validate.mjs`). The iOS screens are all Free today |

**iPad note (re-checked on `main` after #287).** Both the native app
(`native/ios/Config/Base.xcconfig` and the project) and the Capacitor project declare
`TARGETED_DEVICE_FAMILY = 1,2` (iPhone and iPad), so App Store Connect requires 13" iPad
screenshots and the pipeline keeps the `apple-ipad-13` target. Nothing was changed. Making the app
iPhone-only is Kenneth's release decision (it changes who can install the app); only after that
decision remove the target and run `capture-ios.mjs --no-tablet`.

## Google Play

| Item | Requirement | DINCR decision |
|---|---|---|
| Phone screenshots | 2 to 8 per device type. JPEG or 24-bit PNG (no alpha). Each side 320–3840 px. The long side is at most 2× the short side | `google-phone` at **1440×2560** (9:16) |
| Promotion eligibility | At least **4** screenshots of at least **1080 px**, 9:16 portrait (≥ 1080×1920) | 8 screens at 1440×2560 per language |
| Tablets / Chromebook | At least 4, sides 1080–7680 px, 9:16 or 16:9, **only if you target large screens** | Not generated. Add targets if the native app ships a tablet layout |
| Feature graphic | **1024×500**, JPEG or 24-bit PNG (no alpha) | `google-feature-graphic` (brand only, no UI) |
| App icon | 512×512, 32-bit PNG, ≤ 1024 KB | Out of scope (the app icon has its own pipeline) |
| Content | Must show the real in-app experience. **No device frames**. Taglines ≤ **20%** of the image. No calls to action ("Download now", "Install now", "Try now"…), no "Best", "#1", "Top", "New", "Discount", "Sale", "Million downloads". No store badges | Frameless layout; caption band measured ≤ 20% (conservatively, as a share of the height); banned phrases checked in both languages |

## Rules this pipeline adds (from `PRODUCT.md` and `CLAUDE.md`)

- Real UI only. The only app UI in an image is a real capture of the native app (#287 or later). Templates never draw UI.
- Each paid feature is shown with the lowest plan that includes it and labelled with that plan (Basic: budget, strategy; VIP: home, mail).
- Synthetic data only: fixture mode, invented names and amounts, `example.com` mail. No production, no real account, no real financial data.
- No testimonials, user counts, press quotes or certifications (none exist; `PRODUCT.md`).
- Voseo Spanish; calm, non-alarmist tone.
- Public app only: never Owner/JARVIS screens.
