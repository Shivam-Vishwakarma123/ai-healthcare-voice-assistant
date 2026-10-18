import assert from "node:assert/strict";
import { test } from "node:test";
import { applyTheme, normalizeThemePreference, persistThemePreference, readThemePreference } from "../src/services/theme.js";

test("theme preference is normalized and defaults safely to system", () => {
  assert.equal(normalizeThemePreference("dark"), "dark");
  assert.equal(normalizeThemePreference("sepia"), "system");
  assert.equal(readThemePreference({ getItem: () => null }), "system");
});

test("theme preference persists and applies an explicit selection", () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) };
  assert.equal(persistThemePreference("dark", storage), true);
  assert.equal(readThemePreference(storage), "dark");
  const root = { dataset: {}, style: {} };
  assert.equal(applyTheme("dark", root, { matches: false }), "dark");
  assert.equal(root.dataset.theme, "dark");
  assert.equal(root.style.colorScheme, "dark");
});

test("system preference follows the supplied operating-system color scheme", () => {
  const root = { dataset: {}, style: {} };
  assert.equal(applyTheme("system", root, { matches: true }), "dark");
  assert.equal(root.dataset.theme, "dark");
  assert.equal(applyTheme("system", root, { matches: false }), "light");
});
