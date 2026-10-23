export const THEME_PREFERENCES = ["system", "light", "dark"];

// Validates theme preference strings ensuring only 'system', 'light', or 'dark' are recognized.
export function normalizeThemePreference(value) {
  return THEME_PREFERENCES.includes(value) ? value : "system";
}

// Applies theme CSS dataset attributes and color-scheme properties based on preference and OS media queries.
export function applyTheme(preference, root = document.documentElement, media = window.matchMedia("(prefers-color-scheme: dark)")) {
  const normalized = normalizeThemePreference(preference);
  const resolved = normalized === "system" ? (media.matches ? "dark" : "light") : normalized;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  return resolved;
}

// Retrieves persisted theme preference from browser storage with fallback to system defaults.
export function readThemePreference(storage = globalThis.localStorage) {
  try {
    return normalizeThemePreference(storage.getItem("carevoice_theme"));
  } catch {
    return "system";
  }
}

// Saves chosen theme preference into persistent browser storage with error resilience.
export function persistThemePreference(value, storage = globalThis.localStorage) {
  const preference = normalizeThemePreference(value);
  try {
    storage.setItem("carevoice_theme", preference);
  } catch {
    return false;
  }
  return true;
}
