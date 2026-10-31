import type { Settings } from "./SettingsContext";

/** Settings the user changed and has not saved. Everything else shows the saved value. */
export type SettingsEdits = Partial<Omit<Settings, "providers">> & {
  providers?: Record<string, { enabled?: boolean; credentials?: Record<string, string> }>;
};

/** The form: saved settings with the unsaved edits laid over, so a save elsewhere cannot lose them. */
export function withEdits(settings: Settings, edits: SettingsEdits): Settings {
  const providers = { ...settings.providers };
  for (const [id, edit] of Object.entries(edits.providers ?? {})) {
    const saved = providers[id] ?? { enabled: false, credentials: {} };
    providers[id] = { ...saved, ...edit, credentials: { ...saved.credentials, ...edit.credentials } };
  }
  return { ...settings, ...edits, providers };
}
