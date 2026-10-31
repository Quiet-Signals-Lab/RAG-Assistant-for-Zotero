import React, { useState } from "react";
import { useDesk } from "../desk/DeskContext";
import { opening } from "../desk/parts";

/**
 * The context folder: items added from search, each with the passage that
 * matched. Attached items are the only ones RAG Chat answers from.
 */
const ContextTray: React.FC = () => {
  const desk = useDesk();
  const entries = desk.context;
  const attached = entries.filter((e) => e.attached).length;
  const [confirming, setConfirming] = useState(false);
  return (
    <section className={entries.length ? "context-tray context-tray--filled" : "context-tray"} aria-label="Context">
      <div className="context-tray__head">
        <span className="desk-label">
          Context · {entries.length} item{entries.length === 1 ? "" : "s"}{entries.length ? ` · ${attached} attached` : ""}
        </span>
        {entries.length > 0 && (confirming ? (
          <span>
            <button type="button" className="btn btn--danger" onClick={() => { desk.clearContext(); setConfirming(false); }}>
              Clear all {entries.length}
            </button>{" "}
            <button type="button" className="btn" onClick={() => setConfirming(false)}>Keep them</button>
          </span>
        ) : (
          <button type="button" className="link-button" onClick={() => setConfirming(true)}>Clear</button>
        ))}
      </div>
      {entries.length === 0 ? (
        <p className="context-tray__empty">Add items from search with “Add to context”. Attached items are the only ones RAG Chat answers from.</p>
      ) : (
        <ul className="context-tray__list">
          {entries.map((e) => (
            <li key={e.id} className="context-tray__row">
              <label>
                <input type="checkbox" checked={e.attached} onChange={(ev) => desk.setAttached(e.id, ev.target.checked)} />
                <span className="context-tray__label">{e.label}</span>
                {e.page ? <span className="mono"> p. {e.page}</span> : null}
                <span className="context-tray__opening"> · “{opening(e.text)}”</span>
              </label>
              <button type="button" className="context-tray__remove" onClick={() => desk.removeFromContext(e.id)} aria-label={`Remove ${e.label} from the context`}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default ContextTray;
