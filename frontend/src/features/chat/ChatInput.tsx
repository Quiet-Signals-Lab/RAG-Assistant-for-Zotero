import React, { useState, useEffect } from "react";

interface Props {
  onSend: (content: string) => void;
  onStop: () => void;
  disabled?: boolean;
}

const ChatInput: React.FC<Props> = ({ onSend, onStop, disabled }) => {
  const [value, setValue] = useState("");

  useEffect(() => {
    function onInsert(e: Event) {
      try {
        const text = (e as CustomEvent<{ text?: string }>).detail?.text;
        if (text) setValue((v) => (v ? v + "\n" + text : text));
      } catch (err) {
        // ignore
      }
    }
    window.addEventListener("zotero:insert-snippet", onInsert as EventListener);
    return () => window.removeEventListener("zotero:insert-snippet", onInsert as EventListener);
  }, []);

  function submit() {
    if (!value.trim()) return;
    onSend(value);
    setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !disabled) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="chat-view__input">
      <div className="chat-input__wrapper">
        <textarea
          className="chat-input__textarea"
          placeholder="Ask a question about your Zotero library…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        {disabled ? (
          <button className="btn btn--danger" onClick={onStop}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: "6px" }}>
              <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>
            </svg>
            Stop
          </button>
        ) : (
          <button className="btn btn--primary" onClick={submit} disabled={!value.trim()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: "6px" }}>
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Send
          </button>
        )}
      </div>
    </div>
  );
};

export default ChatInput;
