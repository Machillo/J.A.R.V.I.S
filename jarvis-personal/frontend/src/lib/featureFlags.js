import { API_URL } from "./apiUrl";
import { authenticatedFetch } from "./authenticatedFetch";

const CACHE_KEY = "finva:operational-feature-flags:v1";

export const SAFE_FEATURE_DEFAULTS = {
  financial_writes: { flag_key:"financial_writes", enabled:false, safe_default_enabled:false, disabled_message_es:"Los cambios financieros están pausados temporalmente. Tus datos guardados siguen disponibles.", disabled_message_en:"Financial changes are temporarily paused. Your saved data remains available." },
  gmail_automation: { flag_key:"gmail_automation", enabled:false, safe_default_enabled:false, disabled_message_es:"La automatización de Gmail está en mantenimiento temporal.", disabled_message_en:"Gmail automation is temporarily under maintenance." },
  vip_intelligence: { flag_key:"vip_intelligence", enabled:true, safe_default_enabled:true, disabled_message_es:"La inteligencia VIP está en mantenimiento temporal.", disabled_message_en:"VIP intelligence is temporarily under maintenance." },
  advanced_reports: { flag_key:"advanced_reports", enabled:true, safe_default_enabled:true, disabled_message_es:"Los reportes avanzados están en mantenimiento temporal.", disabled_message_en:"Advanced reports are temporarily under maintenance." },
  store_billing: { flag_key:"store_billing", enabled:false, safe_default_enabled:false, disabled_message_es:"Las compras y restauraciones están pausadas temporalmente.", disabled_message_en:"Purchases and restores are temporarily paused." },
};

function asMap(rows = []) {
  return rows.reduce((result, row) => {
    if (row?.flag_key && SAFE_FEATURE_DEFAULTS[row.flag_key]) result[row.flag_key] = row;
    return result;
  }, { ...SAFE_FEATURE_DEFAULTS });
}

export function cachedFeatureFlags() {
  try {
    const cached = JSON.parse(window.localStorage.getItem(CACHE_KEY) || "null");
    return cached && typeof cached === "object" ? { ...SAFE_FEATURE_DEFAULTS, ...cached } : null;
  } catch {
    return null;
  }
}

export async function getOperationalFeatureFlags() {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await authenticatedFetch(`${API_URL}/product-ops/feature-flags`, {
      cache: "no-store", headers: { Accept:"application/json" }, signal:controller.signal,
    });
    if (!response.ok) throw new Error(`Feature flags request failed (${response.status})`);
    const flags = asMap((await response.json())?.flags);
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(flags));
    return flags;
  } catch {
    return cachedFeatureFlags() || { ...SAFE_FEATURE_DEFAULTS };
  } finally {
    window.clearTimeout(timeout);
  }
}

export function featureEnabled(flags, flagKey) {
  if (!flags) return true;
  return Boolean((flags[flagKey] || SAFE_FEATURE_DEFAULTS[flagKey])?.enabled);
}

export function featureDisabledMessage(flags, flagKey, language = "es") {
  const flag = flags?.[flagKey] || SAFE_FEATURE_DEFAULTS[flagKey];
  return language === "en" ? flag?.disabled_message_en : flag?.disabled_message_es;
}
