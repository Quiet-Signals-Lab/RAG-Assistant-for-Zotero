import React from "react";
import { useSettings } from "../../contexts/SettingsContext";

/** The one mode choice of the app, as a segmented control beside the brand: Search or RAG Chat. */
const ModeSwitch: React.FC = () => {
  const { settings, updateSettings } = useSettings();
  const mode = settings.interfaceMode === "chat" ? "chat" : "desk";
  return (
    <div className="segmented" role="group" aria-label="Mode">
      {([["desk", "Search"], ["chat", "RAG Chat"]] as const).map(([id, label]) => (
        <button key={id} type="button" data-mode={id} aria-pressed={mode === id} onClick={() => mode !== id && updateSettings({ interfaceMode: id })}>
          {label}
        </button>
      ))}
    </div>
  );
};

export default ModeSwitch;
