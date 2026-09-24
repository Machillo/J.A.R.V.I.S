# DINCR public landing

Run `npm run build:landing` from `frontend`. Deploy **only** `landing-dist/` as the public site. Do not deploy the application `dist/` on the landing domain. The static build contains no login, APIs, private app bundle, PostHog, or service worker.

The canonical origin in `landing/config.json` is `https://dincr.com`. Store links remain disabled until official URLs are supplied. Public contacts are `soporte@dincr.com` for general support and `privacidad@dincr.com` for data privacy. Mail delivery and forwarding must be verified in the email provider; they are not configured by this repository.

Cloudflare Pages (Git integration): repository `Machillo/J.A.R.V.I.S`, production branch `main`, framework preset **None**, root directory `jarvis-personal/frontend`, build command `npm ci && npm run build:landing`, output directory `landing-dist`, no environment variables. Add the custom domain manually after reviewing the deployment; this build does not change DNS. Pages serves each route's `index.html` and the generated root `404.html` prevents SPA fallback. Never select `dist` as the output. Vercel continues to build the app separately for internal previews.

The legal pages are rendered from `src/pages/PublicInfoPage.jsx` at build time, with the version read from the same source. Prices come from `config.json` and `npm run test:landing` checks them against `backend/product_ops/service.py`. The review block is disabled until authentic, authorized data is configured.

Content rules, enforced by `scripts/test-dincr-public-contract.mjs`:
- **Brand:** public brand DINCR only. The icon is `apple-touch-icon.png` / `favicon-32.png`, never the legacy "J" `favicon.svg`.
- **Claims must match `main`:** no generative-AI marketing, invented numbers, fake reviews or partner logos, and no "Owner" plan.
- **Store availability:** there are no placeholder store badges. While `googlePlayUrl`/`appStoreUrl` are empty, the site says the launch is upcoming.
- **No tracking:** no JavaScript besides structured data, and no analytics on the public site.
- **Screenshots:** the hero shows a labeled illustration with sample data until `heroScreenshot` (a real app capture, with width/height) is set in `config.json`. Needed capture: DINCR Home on a phone (Free or VIP) with synthetic data, about 600×1300 px.

This is an isolated static entry within the existing frontend repository because its existing Vite root loads the private app and telemetry on `/`. It does not change Capacitor routes or the deployed app.
