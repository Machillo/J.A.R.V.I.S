export const COLOR_MODE_STORAGE_KEY = "finva-color-mode";
export const COLOR_MODES = ["dark", "light", "system"];

export const resolveColorMode = (mode) => (
  mode === "system"
    ? (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
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

export const initializeColorMode = () => applyColorMode(getSavedColorMode());
