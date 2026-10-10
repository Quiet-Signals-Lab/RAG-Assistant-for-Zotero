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
      <label htmlFor="chat-question" className="chat-input__label">Your question</label>
      <div className="chat-input__wrapper">
        <textarea
          id="chat-question"
          className="chat-input__textarea"
          placeholder="Ask about your Zotero library…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={2}
        />
        {disabled ? (
          <button type="button" className="btn btn--danger" onClick={onStop}>Stop</button>
        ) : (
          <button type="button" className="btn btn--primary" onClick={submit} disabled={!value.trim()}>Ask</button>
        )}
      </div>
      <p className="chat-input__hint" aria-hidden="true">⏎ to ask · ⇧⏎ for a new line</p>
    </div>
  );
};

export default ChatInput;
