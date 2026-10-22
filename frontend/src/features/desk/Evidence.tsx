import React, { useState } from "react";
import Chain from "./Chain";
import { useDesk, type Pin } from "./DeskContext";
import { BandMark, Highlighted, opening, openPdf, Reference, showInZotero } from "./parts";

function pinLine(p: Pin): string {
  const text = p.text.replace(/\s+/g, " ").trim();
  return `${p.label}${p.page ? `, p. ${p.page}` : ""}: “${text}”`;
}

const ReadingList: React.FC = () => {
  const desk = useDesk();
  const [note, setNote] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const count = desk.pins.length;
  async function copy() {
    try {
      await navigator.clipboard.writeText(desk.pins.map(pinLine).join("\n\n"));
      setNote(`Copied ${desk.pins.length} passages`);
    } catch {
      setNote("Could not reach the clipboard");
    }
    window.setTimeout(() => setNote(null), 2500);
  }
  return (
    <details className="reading-list" open={count > 0}>
      <summary>
        <div className="panel-head">
          <h2 className="panel-head__title">Reading list</h2>
          <span className={count ? "reading-list__count" : "panel-head__hint"}>{count ? `● ${count} pinned` : "nothing pinned yet"}</span>
        </div>
      </summary>
      {count === 0 ? (
        <p className="reading-list__empty">Pin a passage to keep it here, with its page, across searches.</p>
      ) : (
        <>
      <ul className="reading-list__items">
        {desk.pins.map((p) => {
          const inResults = desk.result?.items.some((it) => it.item_id === p.itemId);
          return (
            <li key={p.id}>
              {inResults ? (
                <button type="button" className="link-button" onClick={() => desk.select(p.itemId)}>
                  {p.label}
                </button>
              ) : (
                <span>{p.label}</span>
              )}
              {p.page ? <span className="mono"> p. {p.page}</span> : null}
              <span className="reading-list__opening"> · “{opening(p.text)}”</span>
            </li>
          );
        })}
      </ul>
      <div className="reading-list__actions">
        <button type="button" className="btn" onClick={copy}>Copy passages</button>
        <button type="button" className="btn" onClick={desk.addPinsToContext}>Add pinned to context</button>
        {confirming ? (
          <>
            <button type="button" className="btn btn--danger" onClick={() => { desk.clearPins(); setConfirming(false); }}>
              Clear all {count}
            </button>
            <button type="button" className="btn" onClick={() => setConfirming(false)}>Keep them</button>
          </>
        ) : (
          <button type="button" className="link-button" onClick={() => setConfirming(true)}>Clear</button>
        )}
      </div>
      <div role="status" aria-live="polite" className="reading-list__note">{note}</div>
        </>
      )}
    </details>
  );
};

const Evidence: React.FC = () => {
  const desk = useDesk();
  const item = desk.selected;
  const inContext = !!item && desk.inContext(item.item_id);
  const [failure, setFailure] = useState<string | null>(null);

  const open = (page?: number | null) => {
    if (!item) return;
    setFailure(null);
    openPdf(item, page).catch((e) => setFailure(e instanceof Error ? e.message : "Could not open the PDF."));
  };

  return (
    <div
      className="evidence"
      id="desk-evidence"
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === "Escape" || e.key === "ArrowLeft") {
          desk.setPane("browse");
          (document.querySelector(`.row__select[data-item="${item?.item_id ?? ""}"]`) as HTMLElement | null)?.focus();
        }
      }}
    >
      <ReadingList />

      <div className="panel-head">
        <h2 className="panel-head__title">Evidence{item ? ` · result ${item.rank}` : ""}</h2>
        <button type="button" className="evidence__close btn" onClick={() => desk.setPane("browse")}>
          Back to the list
        </button>
      </div>

      {!item ? (
        <p className="evidence__empty">Choose a result to see the passages that matched, page by page.</p>
      ) : (
        <>
          <div className="evidence__item">
            <p className="evidence__ref"><Reference item={item} /></p>
            <div className="evidence__actions">
              {(item.citation?.pdf_key || item.pdf_path) && (
                <button type="button" className="btn btn--primary" onClick={() => open(item.passages[0]?.page)}>
                  Open PDF{item.passages[0]?.page ? ` p. ${item.passages[0].page}` : ""}
                </button>
              )}
              {item.citation && <button type="button" className="btn" onClick={() => showInZotero(item.citation)}>Show in Zotero</button>}
              <button type="button" className="btn" onClick={() => desk.moreLike(item)}>More like this</button>
              <button
                type="button"
                className="btn btn--context"
                aria-pressed={inContext}
                title={inContext ? "In the RAG Chat context. Click to remove it." : "Add this item and its matched passage to the RAG Chat context"}
                onClick={() => (inContext ? desk.removeFromContext(item.item_id) : desk.addToContext([item]))}
              >
                {inContext ? "Added to context" : "Add to context"}
              </button>
            </div>
            {failure && <p className="desk-notice desk-notice--error">{failure}</p>}
            <p className="evidence__count">
              {item.passages.length} passage{item.passages.length === 1 ? "" : "s"}, strongest first
            </p>
          </div>

          {item.passages.length === 0 ? (
            <p className="evidence__empty">Matched by scope only: no passage in this item matched the query.</p>
          ) : (
            <ol className="passages">
              {item.passages.map((passage, i) => {
                const pinned = desk.isPinned(item, passage);
                return (
                  <li key={`${passage.page}-${i}`} className={pinned ? "passage passage--pinned" : "passage"}>
                    <p className="passage__text">
                      <Highlighted text={passage.text} spans={passage.highlights} />
                    </p>
                    <div className="passage__meta">
                      {passage.page ? (
                        <button type="button" className="link-button mono" onClick={() => open(passage.page)} title="Open the PDF at this page">
                          p. {passage.page}
                        </button>
                      ) : (
                        <span className="mono">page unknown</span>
                      )}
                      <BandMark band={passage.band} small withLabel />
                      {pinned && <span className="passage__pinned">● Pinned</span>}
                      <button type="button" className="btn passage__pin" aria-pressed={pinned} onClick={() => desk.togglePin(item, passage)}>
                        {pinned ? "Unpin" : "Pin"}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </>
      )}

      {item && <Chain key={item.item_id} item={item} />}
    </div>
  );
};

export default Evidence;
