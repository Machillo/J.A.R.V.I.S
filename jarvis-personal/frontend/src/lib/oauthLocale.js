// Language of the provider's sign-in and consent screens. DINCR ships English and
// Spanish; anything else falls back to English. The backend normalizes the value again
// before it reaches the authorization URL (Google's documented `hl` parameter).

const SUPPORTED = new Set(["en", "es"]);
const FALLBACK = "en";

/** "en-GB" → "en", "es-419" → "es", unknown → "en"; empty → null (no opinion). */
export function normalizeOAuthLocale(value) {
  const tag = String(value ?? "").trim().toLowerCase().replace(/_/g, "-");
  if (!tag) return null;
  const primary = tag.split("-")[0];
  return SUPPORTED.has(primary) ? primary : FALLBACK;
}

/**
 * The first non-empty source decides, in this order: an explicit preference saved by
 * DINCR, the app's current language, then the device languages. English when none is known.
 */
export function getOAuthLocale({
  preference,
  appLanguage,
  languages = typeof navigator === "undefined" ? [] : navigator.languages,
  language = typeof navigator === "undefined" ? undefined : navigator.language,
} = {}) {
  const candidates = [preference, appLanguage, ...(Array.isArray(languages) ? languages : []), language];
  for (const candidate of candidates) {
    const locale = normalizeOAuthLocale(candidate);
    if (locale) return locale;
  }
  return FALLBACK;
}
