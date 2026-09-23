import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";

// Official public copies of the legal documents (same text and version as the app).
export const LEGAL_URLS = {
  terms: "https://dincr.com/terminos/",
  privacy: "https://dincr.com/privacidad/",
};

// Inside the native app a same-origin link (/terms) replaced the whole app WebView
// with a web page it could not scroll or leave. Open the public site in the system
// in-app browser instead: native scrolling and a clear close button back to DINCR.
export function openLegalDocument(event, kind) {
  const url = LEGAL_URLS[kind];
  if (!url || !Capacitor.isNativePlatform()) return; // web: the anchor opens a new tab
  event.preventDefault();
  Browser.open({ url, presentationStyle: "popover" }).catch(() => window.open(url, "_system"));
}
