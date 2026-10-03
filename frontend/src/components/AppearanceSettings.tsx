import { Check, Moon, Sun, Monitor, Type } from "lucide-react";
import {
  useAppearance,
  type Theme,
  type FontSize,
} from "../appearance/AppearanceProvider";

export function AppearanceSettings() {
  const { theme, setTheme, fontSize, setFontSize } = useAppearance();
  return (
    <section
      className="card appearance-settings"
      aria-labelledby="appearance-heading"
    >
      <div className="card-title">
        <div>
          <h2 id="appearance-heading">Appearance</h2>
          <p>Changes apply immediately and are saved in this browser.</p>
        </div>
        <Type size={22} />
      </div>
      <div className="appearance-grid">
        <fieldset>
          <legend>Theme</legend>
          <div className="preference-options">
            {(
              [
                ["light", "Light", Sun],
                ["dark", "Dark", Moon],
                ["system", "System", Monitor],
              ] as const
            ).map(([value, label, Icon]) => (
              <label
                key={value}
                className={
                  theme === value ? "preference selected" : "preference"
                }
              >
                <input
                  type="radio"
                  name="appearance-theme"
                  value={value}
                  checked={theme === value}
                  onChange={() => setTheme(value as Theme)}
                />
                <Icon size={18} />
                <span>{label}</span>
                {theme === value && <Check size={16} aria-hidden="true" />}
              </label>
            ))}
          </div>
          <p className="muted">
            System follows your device’s light or dark preference, including
            changes while the app is open.
          </p>
        </fieldset>
        <fieldset>
          <legend>Interface Font Size</legend>
          <div className="preference-options">
            {(["small", "medium", "large"] as const).map((value) => (
              <label
                key={value}
                className={
                  fontSize === value ? "preference selected" : "preference"
                }
              >
                <input
                  type="radio"
                  name="appearance-font-size"
                  value={value}
                  checked={fontSize === value}
                  onChange={() => setFontSize(value as FontSize)}
                />
                <span>{value[0].toUpperCase() + value.slice(1)}</span>
                {fontSize === value && <Check size={16} aria-hidden="true" />}
              </label>
            ))}
          </div>
          <p className="muted">
            Scales typography throughout the interface. Tables stay scrollable
            at larger sizes.
          </p>
        </fieldset>
      </div>
    </section>
  );
}
