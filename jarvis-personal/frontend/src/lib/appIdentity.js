// DINCR is the only public app: com.dincr.app on Android and iOS.
export const DINCR_APP_ID = "com.dincr.app";
// Transitional only: the backend still returns mail OAuth to this scheme
// (FINVA_GMAIL_RETURN_URL). It never identifies a build.
export const LEGACY_MAIL_CALLBACK_SCHEME = "com.finva.app";

export const isDincrAppId = (id) => id === DINCR_APP_ID;

export const nativeAppId = import.meta.env?.VITE_NATIVE_APP_ID || DINCR_APP_ID;
export const isDincrDistribution = isDincrAppId(nativeAppId);

// Accept the mail OAuth return on the canonical scheme and on the transitional one.
const MAIL_OAUTH_CALLBACKS = [DINCR_APP_ID, LEGACY_MAIL_CALLBACK_SCHEME].map((id) => `${id}://gmail/callback`);
export const isMailOAuthCallback = (url) => MAIL_OAUTH_CALLBACKS.some((prefix) => String(url || "").startsWith(prefix));
