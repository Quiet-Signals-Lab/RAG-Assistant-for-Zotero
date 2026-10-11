import React, { useEffect, useRef, useState } from "react";
import { chain } from "../../api/search";
import type { ChainEntry, ChainResponse, DeskItem } from "../../types/desk";
import { showInZotero } from "./parts";

const SHOWN = 20;

function byline(e: ChainEntry): string {
  const names = e.authors.length > 2 ? `${e.authors[0]} et al.` : e.authors.join(" & ");
  return [names, e.year ? `(${e.year})` : ""].filter(Boolean).join(" ");
}

const Entries: React.FC<{ entries: ChainEntry[]; label: string }> = ({ entries, label }) => {
  const [all, setAll] = useState(false);
  const owned = entries.filter((e) => e.owned_item_id).length;
  if (!entries.length) return <p className="chain__empty">{label}: none listed.</p>;
  return (
    <section className="chain__list" aria-label={label}>
      <h3 className="desk-label desk-label--split">
        <span>{label} · {entries.length}</span>
        {owned > 0 && <span className="desk-label__aside">● {owned} in your library</span>}
      </h3>
      <ol>
        {(all ? entries : entries.slice(0, SHOWN)).map((e, i) => (
          <li key={`${e.title}-${i}`} className={e.owned_item_id ? "chain__entry chain__entry--owned" : "chain__entry"}>
            <span className="chain__mark" aria-hidden="true">{e.owned_item_id ? "●" : ""}</span>
            <span className="chain__text">
              {byline(e) && <span className="chain__byline">{byline(e)}. </span>}
              {e.owned_item_id && e.citation ? (
                <button type="button" className="link-button" onClick={() => showInZotero(e.citation)} title="In your library: show it in Zotero">
                  {e.title}
                </button>
              ) : e.url ? (
                <a href={e.url} target="_blank" rel="noreferrer">{e.title}</a>
              ) : (
                e.title
              )}
              {e.owned_item_id && <span className="sr-only"> (in your library)</span>}
            </span>
          </li>
        ))}
      </ol>
      {entries.length > SHOWN && (
        <button type="button" className="btn" onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer" : `Show all ${entries.length}`}
        </button>
      )}
    </section>
  );
};

/**
 * Footnote chasing and citation searching (Bates): the works an item cites and the
 * works that cite it, from Semantic Scholar, with the reader's own copies marked.
 * Nothing is sent until the reader asks.
 */
const Chain: React.FC<{ item: DeskItem }> = ({ item }) => {
  const [state, setState] = useState<{ status: "idle" | "loading" | "done" | "error"; data?: ChainResponse; error?: string }>({ status: "idle" });
  const inflight = useRef<AbortController | null>(null);
  useEffect(() => () => inflight.current?.abort(), []);

  function look() {
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    setState({ status: "loading" });
    chain(item.item_id, controller.signal)
      .then((data) => !controller.signal.aborted && setState({ status: "done", data }))
      .catch((e) => !controller.signal.aborted && setState({ status: "error", error: e instanceof Error ? e.message : "The lookup failed." }));
  }

  return (
    <section className="chain" aria-labelledby={`chain-${item.item_id}`}>
      <h2 id={`chain-${item.item_id}`} className="panel-head__title panel-head--rule">References and citations</h2>
      {state.status === "idle" && (
        <>
          <p className="chain__hint">Looks this item up on Semantic Scholar, which needs its DOI or title. Works already in your library are marked.</p>
          <button type="button" className="btn" onClick={look}>Look up on Semantic Scholar</button>
        </>
      )}
      {state.status === "loading" && <p className="loading-rule">Asking Semantic Scholar…</p>}
      {state.status === "error" && (
        <div className="desk-notice desk-notice--error">
          <p>{state.error}</p>
          <button type="button" className="btn" onClick={look}>Try again</button>
        </div>
      )}
      {state.status === "done" && state.data && !state.data.found && (
        <p className="chain__empty">Semantic Scholar does not list this item.</p>
      )}
      {state.status === "done" && state.data?.found && (
        <>
          <Entries entries={state.data.references ?? []} label="References" />
          <Entries entries={state.data.cited_by ?? []} label="Cited by" />
          {state.data.url && (
            <p className="chain__source">
              From <a href={state.data.url} target="_blank" rel="noreferrer">Semantic Scholar</a>. Its lists can be incomplete.
            </p>
          )}
        </>
      )}
    </section>
  );
};

export default Chain;
