// Focused lifecycle check without installing a frontend test framework.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");
const effects = [];
const mediaListeners = new Set();
const storageListeners = new Set();
const saved = new Map();
const root = { dataset: {}, style: {} };
const media = {
  matches: false,
  addEventListener: (_, callback) => mediaListeners.add(callback),
  removeEventListener: (_, callback) => mediaListeners.delete(callback),
};
const react = {
  createContext: () => ({ Provider: "provider" }),
  useState: (initial) => [initial(), () => {}],
  useEffect: (effect) => effects.push(effect),
  useContext: () => null,
};
const context = {
  exports: {},
  require: (name) => (name === "react" ? react : { jsx: () => null }),
  document: { documentElement: root },
  window: {
    matchMedia: () => media,
    addEventListener: (_, callback) => storageListeners.add(callback),
    removeEventListener: (_, callback) => storageListeners.delete(callback),
  },
  localStorage: {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
  },
};
const source = fs.readFileSync("src/appearance/AppearanceProvider.tsx", "utf8");
vm.runInNewContext(
  ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText,
  context,
);
const { initializeAppearance, AppearanceProvider, applyAppearance } =
  context.exports;
initializeAppearance();
assert.equal(root.dataset.theme, "light");
assert.equal(root.dataset.fontSize, "medium");
AppearanceProvider({ children: null });
const cleanup = effects.map((effect) => effect()).filter(Boolean);
assert.equal(saved.get("annopilot-theme"), "system");
assert.equal(saved.get("annopilot-font-size"), "medium");
media.matches = true;
mediaListeners.forEach((callback) => callback());
assert.equal(
  root.dataset.theme,
  "dark",
  "System must react to live OS changes",
);
media.matches = false;
mediaListeners.forEach((callback) => callback());
assert.equal(root.dataset.theme, "light");
applyAppearance("dark", "large", false);
assert.equal(root.dataset.theme, "dark");
assert.equal(root.dataset.fontSize, "large");
assert.equal(root.style.colorScheme, "dark");
saved.set("annopilot-theme", "invalid");
saved.set("annopilot-font-size", "invalid");
initializeAppearance();
assert.equal(root.dataset.theme, "light");
assert.equal(root.dataset.fontSize, "medium");
cleanup.forEach((callback) => callback());
assert.equal(mediaListeners.size, 0);
assert.equal(storageListeners.size, 0);
console.log(
  "Appearance defaults, persistence, live System changes, overrides, fallback and cleanup: PASS",
);
