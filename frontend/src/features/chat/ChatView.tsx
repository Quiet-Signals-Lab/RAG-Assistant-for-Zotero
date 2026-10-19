import React from "react";
import { useChatContext } from "../../contexts/ChatContext";
import ChatMessages from "./ChatMessages";
import ChatInput from "./ChatInput";
import ErrorBanner from "../../components/feedback/ErrorBanner";
import { useSessions } from "../../contexts/SessionsContext";
import { useSettings } from "../../contexts/SettingsContext";

const ChatView: React.FC = () => {
  const { messages, loading, error, sendMessage, stopGeneration } = useChatContext();
  const { currentSessionId, getSession } = useSessions();
  const { updateSettings } = useSettings();
  const scope = currentSessionId ? getSession(currentSessionId)?.itemIds : undefined;

  return (
    <div className="chat-view">
      {error && (
        <div className="chat-view__error">
          <ErrorBanner message={error} />
        </div>
      )}
      {scope && scope.length > 0 && (
        <p className="desk-notice chat-view__scope">
          Answers come only from the {scope.length} item{scope.length === 1 ? "" : "s"} you chose in search.{" "}
          <button type="button" className="link-button" onClick={() => updateSettings({ interfaceMode: "desk" })}>Back to search</button>
        </p>
      )}
      <ChatMessages messages={messages} loading={loading} />
      <ChatInput onSend={sendMessage} onStop={stopGeneration} disabled={loading} />
    </div>
  );
};

export default ChatView;
