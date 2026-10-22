import React from "react";
import { useChatContext, attachedContextIds } from "../../contexts/ChatContext";
import ChatMessages from "./ChatMessages";
import ChatInput from "./ChatInput";
import ChatTitle from "./ChatTitle";
import ContextTray from "./ContextTray";
import ErrorBanner from "../../components/feedback/ErrorBanner";
import { useSessions } from "../../contexts/SessionsContext";
import { useDesk } from "../desk/DeskContext";

const ChatView: React.FC = () => {
  const { messages, loading, error, sendMessage, stopGeneration } = useChatContext();
  const { currentSessionId, getSession } = useSessions();
  const desk = useDesk();
  const attached = attachedContextIds(desk.context);
  const sessionScope = currentSessionId ? getSession(currentSessionId)?.itemIds : undefined;
  const scope = attached ?? sessionScope;

  return (
    <div className="chat-view">
      <ChatTitle />
      {error && (
        <div className="chat-view__error">
          <ErrorBanner message={error} />
        </div>
      )}
      {scope && scope.length > 0 && (
        <p className="desk-notice chat-view__scope">
          Answers come only from the {scope.length} item{scope.length === 1 ? "" : "s"} {attached ? "attached in the context below" : "you chose in search"}.
        </p>
      )}
      <ChatMessages messages={messages} loading={loading} />
      <ContextTray />
      <ChatInput onSend={sendMessage} onStop={stopGeneration} disabled={loading} />
    </div>
  );
};

export default ChatView;
