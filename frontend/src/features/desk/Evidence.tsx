import React, { useState } from "react";
import Chain from "./Chain";
import { useDesk, type Pin } from "./DeskContext";
import { BandMark, ClerkNoteLine, Highlighted, openPdf, Reference, showInZotero } from "./parts";

/** The first few words of a passage, enough to tell two pins from one page apart. */
function opening(text: string): string {
  const words = text.replace(/^…/, "").split(/\s+/).filter(Boolean);
  return words.slice(0, 6).join(" ") + (words.length > 6 ? "…" : "");
}

function pinLine(p: Pin): string {
  const text = p.text.replace(/\s+/g, " ").trim();
  return `${p.label}${p.page ? `, p. ${p.page}` : ""}: “${text}”`;
}

const ReadingList: React.FC = () => {
  const desk = useDesk();
  const [note, setNote] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  if (desk.pins.length === 0) {
    return (
      <section className="reading-list" aria-labelledby="reading-heading">
        <h2 id="reading-heading" className="panel-head__title panel-head--rule">Reading list</h2>
        <p className="reading-list__empty">Pin a passage to keep it here, with its page, across searches.</p>
      </section>
    );
  }
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
    <section className="reading-list" aria-labelledby="reading-heading">
      <h2 id="reading-heading" className="panel-head__title panel-head--rule panel-head--split">
        <span>Reading list</span>
        <span className="reading-list__count">● {desk.pins.length} pinned</span>
      </h2>
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
        <button type="button" className="btn btn--primary" onClick={copy}>Copy passages</button>
        {confirming ? (
          <>
            <button type="button" className="btn btn--danger" onClick={() => { desk.clearPins(); setConfirming(false); }}>
              Clear all {desk.pins.length}
            </button>
            <button type="button" className="btn" onClick={() => setConfirming(false)}>Keep them</button>
          </>
        ) : (
          <button type="button" className="btn" onClick={() => setConfirming(true)}>Clear</button>
        )}
      </div>
      <div role="status" aria-live="polite" className="reading-list__note">{note}</div>
    </section>
  );
};

const Evidence: React.FC = () => {
  const desk = useDesk();
  const item = desk.selected;
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
            </div>
            {desk.clerk.notes[item.item_id] && (
              <p className="evidence__note">
                <ClerkNoteLine note={desk.clerk.notes[item.item_id]} onPage={(page) => open(page)} />
              </p>
            )}
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

      <ReadingList />
    </div>
  );
};

export default Evidence;
