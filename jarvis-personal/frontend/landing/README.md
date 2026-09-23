# DINCR public landing

Run `npm run build:landing` from `frontend`. Deploy **only** `landing-dist/` as the public site. Do not deploy the application `dist/` on the landing domain. The static build contains no login, APIs, private app bundle, PostHog, or service worker.

Set values in `landing/config.json` before publishing. `baseUrl` must be the final HTTPS origin. Without it the build deliberately emits no canonical, sitemap URLs, or absolute social metadata. Store links remain disabled until supplied.

The legal pages are rendered verbatim from the current `src/pages/PublicInfoPage.jsx` legal sections at build time. Review these legal texts and the public support channel with the product owner before publication. The source currently names J.A.R.V.I.S. and lists VIP at ₡5.990, conflicting with the candidate ₡4.990. The price cards explicitly label the prices as proposals and omit structured offers until reconciled. The review block is disabled until authentic, authorized data is configured.

This is an isolated static entry within the existing frontend repository because its existing Vite root loads the private app and telemetry on `/`. It does not change Capacitor routes or the deployed app.
