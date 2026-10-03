import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Theme = "light" | "dark" | "system";
export type FontSize = "small" | "medium" | "large";
const themes: Theme[] = ["light", "dark", "system"];
const fontSizes: FontSize[] = ["small", "medium", "large"];

function readPreference<T extends string>(
  key: string,
  allowed: T[],
  fallback: T,
): T {
  try {
    const value = localStorage.getItem(key);
    return allowed.includes(value as T) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Preferences still apply if storage is unavailable. */
  }
}

export function applyAppearance(
  theme: Theme,
  fontSize: FontSize,
  systemDark: boolean,
) {
  const root = document.documentElement;
  root.dataset.theme =
    theme === "system" ? (systemDark ? "dark" : "light") : theme;
  root.dataset.fontSize = fontSize;
  root.style.colorScheme = root.dataset.theme;
}

// Run before React renders to avoid a light/dark preference flash.
export function initializeAppearance() {
  applyAppearance(
    readPreference("annopilot-theme", themes, "system"),
    readPreference("annopilot-font-size", fontSizes, "medium"),
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
}

type Preferences = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  fontSize: FontSize;
  setFontSize: (fontSize: FontSize) => void;
};
const AppearanceContext = createContext<Preferences | null>(null);

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() =>
    readPreference("annopilot-theme", themes, "system"),
  );
  const [fontSize, setFontSize] = useState<FontSize>(() =>
    readPreference("annopilot-font-size", fontSizes, "medium"),
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => applyAppearance(theme, fontSize, media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme, fontSize]);
  useEffect(() => persist("annopilot-theme", theme), [theme]);
  useEffect(() => persist("annopilot-font-size", fontSize), [fontSize]);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === "annopilot-theme" || event.key === null)
        setTheme(readPreference("annopilot-theme", themes, "system"));
      if (event.key === "annopilot-font-size" || event.key === null)
        setFontSize(readPreference("annopilot-font-size", fontSizes, "medium"));
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  return (
    <AppearanceContext.Provider
      value={{ theme, setTheme, fontSize, setFontSize }}
    >
      {children}
    </AppearanceContext.Provider>
  );
}

export function useAppearance() {
  const context = useContext(AppearanceContext);
  if (!context) throw new Error("AppearanceProvider is required");
  return context;
}
