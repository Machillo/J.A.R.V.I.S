export const COLOR_MODE_STORAGE_KEY = "finva-color-mode";
export const COLOR_MODES = ["dark", "light", "system"];

// The only source of truth for the theme is html[data-color-mode-resolved]. App CSS
// must never branch on the prefers-color-scheme media query itself: "Automatic" is
// resolved here, so the app setting and the phone setting cannot disagree.
const systemLight = () => window.matchMedia("(prefers-color-scheme: light)");

export const resolveColorMode = (mode) => (
  mode === "system"
    ? (systemLight().matches ? "light" : "dark")
    : mode
);

export const applyColorMode = (mode) => {
  const resolved = resolveColorMode(mode);
  document.documentElement.dataset.colorMode = mode;
  document.documentElement.dataset.colorModeResolved = resolved;
  document.documentElement.style.colorScheme = resolved;
};

export const getSavedColorMode = () => {
  const saved = localStorage.getItem(COLOR_MODE_STORAGE_KEY);
  return COLOR_MODES.includes(saved) ? saved : "system";
};

export const initializeColorMode = () => {
  applyColorMode(getSavedColorMode());
  // "Automatic" follows the phone while the app is open (e.g. scheduled dark mode).
  systemLight().addEventListener?.("change", () => {
    if (getSavedColorMode() === "system") applyColorMode("system");
  });
};
