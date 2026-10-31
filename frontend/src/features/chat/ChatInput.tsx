import React, { useState } from "react";

interface Props {
  onSend: (content: string) => void;
  onStop: () => void;
  disabled?: boolean;
}

const ChatInput: React.FC<Props> = ({ onSend, onStop, disabled }) => {
  const [value, setValue] = useState("");

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
          readOnly={disabled} // disabled would drop focus on every question
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
