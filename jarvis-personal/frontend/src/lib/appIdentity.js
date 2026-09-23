// DINCR is the only public app. iOS ships as com.dincr.app; Android keeps its
// historical com.finva.app package until its own store migration, so both ids
// identify the same DINCR product.
export const DINCR_APP_ID = "com.dincr.app";
export const LEGACY_DINCR_APP_ID = "com.finva.app";
const DINCR_APP_IDS = new Set([DINCR_APP_ID, LEGACY_DINCR_APP_ID]);

export const isDincrAppId = (id) => DINCR_APP_IDS.has(id);

// Builds without an explicit id (Android, web) keep the Android package until it migrates.
// The iOS workflow (scripts/ios-product.mjs) builds with VITE_NATIVE_APP_ID=com.dincr.app.
export const nativeAppId = import.meta.env?.VITE_NATIVE_APP_ID || LEGACY_DINCR_APP_ID;
export const isDincrDistribution = isDincrAppId(nativeAppId);

// The backend returns Gmail/Outlook OAuth to one configured scheme for every
// platform (FINVA_GMAIL_RETURN_URL), so accept the callback on either DINCR scheme.
const MAIL_OAUTH_CALLBACKS = [DINCR_APP_ID, LEGACY_DINCR_APP_ID].map((id) => `${id}://gmail/callback`);
export const isMailOAuthCallback = (url) => MAIL_OAUTH_CALLBACKS.some((prefix) => String(url || "").startsWith(prefix));
