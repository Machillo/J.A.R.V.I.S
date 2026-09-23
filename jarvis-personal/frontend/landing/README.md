# DINCR public landing

Run `npm run build:landing` from `frontend`. Deploy **only** `landing-dist/` as the public site. Do not deploy the application `dist/` on the landing domain. The static build contains no login, APIs, private app bundle, PostHog, or service worker.

The canonical origin in `landing/config.json` is `https://dincr.com`. Store links remain disabled until official URLs are supplied. Public support contact is still pending.

Cloudflare Pages (Git integration): repository `Machillo/J.A.R.V.I.S`, production branch `main`, framework preset **None**, root directory `jarvis-personal/frontend`, build command `npm ci && npm run build:landing`, output directory `landing-dist`, no environment variables. Add the custom domain manually after reviewing the deployment; this build does not change DNS. Pages serves each route's `index.html` and the generated root `404.html` prevents SPA fallback. Never select `dist` as the output. Vercel continues to build the app separately for internal previews.

The legal pages are rendered verbatim from the current `src/pages/PublicInfoPage.jsx` legal sections at build time. Review these legal texts and the public support channel with the product owner before publication. The source currently names J.A.R.V.I.S. and lists VIP at ₡5.990, conflicting with the candidate ₡4.990. The price cards explicitly label the prices as proposals and omit structured offers until reconciled. The review block is disabled until authentic, authorized data is configured.

This is an isolated static entry within the existing frontend repository because its existing Vite root loads the private app and telemetry on `/`. It does not change Capacitor routes or the deployed app.
