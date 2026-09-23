// One-time move of browser storage keys from the former FINVA brand, so web users
// keep their app lock, color mode and dismissed notices. Imported first in main.jsx
// because some modules read storage while loading.
const LEGACY_PREFIX = "finva";

try {
  const storage = window.localStorage;
  for (const key of Object.keys(storage)) {
    if (!key.startsWith(`${LEGACY_PREFIX}:`) && !key.startsWith(`${LEGACY_PREFIX}-`)) continue;
    const next = `dincr${key.slice(LEGACY_PREFIX.length)}`;
    if (storage.getItem(next) === null) storage.setItem(next, storage.getItem(key));
    storage.removeItem(key);
  }
} catch {
  // Storage may be unavailable (private mode, hardened browsers). Never block DINCR.
}
