import React from "react";
import { useChatContext } from "../../contexts/ChatContext";
import ChatMessages from "./ChatMessages";
import ChatInput from "./ChatInput";
import ErrorBanner from "../../components/feedback/ErrorBanner";

const ChatView: React.FC = () => {
  const { messages, loading, error, sendMessage, stopGeneration } = useChatContext();

  return (
    <div className="chat-view">
      {error && (
        <div style={{ padding: "6px 16px" }}>
          <ErrorBanner message={error} />
        </div>
      )}
      <ChatMessages messages={messages} loading={loading} />
      <ChatInput onSend={sendMessage} onStop={stopGeneration} disabled={loading} />
    </div>
  );
};

export default ChatView;
