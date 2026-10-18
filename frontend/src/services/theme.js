export const THEME_PREFERENCES = ["system", "light", "dark"];

export function normalizeThemePreference(value) {
  return THEME_PREFERENCES.includes(value) ? value : "system";
}

export function applyTheme(preference, root = document.documentElement, media = window.matchMedia("(prefers-color-scheme: dark)")) {
  const normalized = normalizeThemePreference(preference);
  const resolved = normalized === "system" ? (media.matches ? "dark" : "light") : normalized;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  return resolved;
}

export function readThemePreference(storage = globalThis.localStorage) {
  try {
    return normalizeThemePreference(storage.getItem("carevoice_theme"));
  } catch {
    return "system";
  }
}

export function persistThemePreference(value, storage = globalThis.localStorage) {
  const preference = normalizeThemePreference(value);
  try {
    storage.setItem("carevoice_theme", preference);
  } catch {
    return false;
  }
  return true;
}
