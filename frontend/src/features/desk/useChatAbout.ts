import { useSessions } from "../../contexts/SessionsContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useDesk } from "./DeskContext";

/** Open the chat on a new session that answers only from these items; null when no model is set up. */
export function useChatAbout(): ((itemIds: string[], title: string) => void) | null {
  const { startSession } = useSessions();
  const { updateSettings } = useSettings();
  const { model } = useDesk();
  if (!model?.available) return null;
  return (itemIds, title) => {
    startSession(title, [...new Set(itemIds)]);
    updateSettings({ interfaceMode: "chat" });
  };
}
