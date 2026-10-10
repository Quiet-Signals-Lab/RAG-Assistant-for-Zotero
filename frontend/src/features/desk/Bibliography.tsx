import React, { useEffect, useMemo, useRef, useState } from "react";
import type { Citation, DeskItem, KnownItem, ScopeFilters } from "../../types/desk";
import { plain, reference, shortCite, sortName } from "./cite";
import { useDesk, type Sort } from "./DeskContext";
import { BandMark, Highlighted, itemTypeLabel, openPdf, pageSpan, Reference, showInZotero } from "./parts";

function sortItems(items: DeskItem[], sort: Sort): DeskItem[] {
  if (sort === "relevance") return items;
  const copy = [...items];
  if (sort === "year") {
    const year = (it: DeskItem) => it.citation?.year ?? it.year ?? -Infinity;
    copy.sort((a, b) => year(b) - year(a) || a.rank - b.rank);
  } else {
    copy.sort((a, b) => sortName(a).localeCompare(sortName(b)) || a.rank - b.rank);
  }
  return copy;
}

function describeScope(scope: ScopeFilters): string {
  const parts: string[] = [];
  if (scope.year_min && scope.year_max) parts.push(`${scope.year_min}–${scope.year_max}`);
  else if (scope.year_min) parts.push(`since ${scope.year_min}`);
  else if (scope.year_max) parts.push(`until ${scope.year_max}`);
  if (scope.tags?.length) parts.push(`tagged ${scope.tags.join(", ")}`);
  if (scope.collections?.length) parts.push(`in ${scope.collections.join(", ")}`);
  return parts.join(", ") || "that limit";
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Catalogue-card author line: "Woodcock, Jamie, and Mark Graham." */
function cardAuthors(c: Citation): string {
  const people = c.creators.filter((x) => x.role !== "editor").length ? c.creators.filter((x) => x.role !== "editor") : c.creators;
  const names = people.map((p, i) => (i === 0 ? [p.last, p.first].filter(Boolean).join(", ") : [p.first, p.last].filter(Boolean).join(" ")));
  const end = (text: string) => (text.endsWith(".") ? text : `${text}.`);
  if (names.length <= 1) return names[0] ? end(names[0]) : "";
  return end(`${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`);
}

/** The one card in the room: the item the reader asked for by name (Cutter's first object). */
const KnownItemCard: React.FC<{ known: KnownItem; others: KnownItem[] }> = ({ known, others }) => {
  const desk = useDesk();
  const c = known.citation;
  if (!c) return null;
  const imprint = [c.container, c.place && c.publisher ? `${c.place} : ${c.publisher}` : c.publisher, c.year].filter(Boolean).join(", ");
  const label = shortCite({ citation: c, title: c.title, authors: "", year: c.year });
  return (
    <section className="catalogue-card" aria-label={`Known item: ${label}`}>
      <div className="catalogue-card__head">
        <span>Known item · pinned above the list</span>
        <span>{c.item_key}</span>
      </div>
      <div className="catalogue-card__body">
        {cardAuthors(c) && <div>{cardAuthors(c)}</div>}
        <div className="catalogue-card__indent">{c.title}{/[.?!]$/.test(c.title) ? "" : "."}</div>
        {imprint && <div className="catalogue-card__indent">{imprint}.</div>}
        <div className="catalogue-card__indent catalogue-card__quiet">
          {itemTypeLabel(c.item_type)}
          {known.indexed ? "" : " · not in the index yet"}
        </div>
      </div>
      <div className="catalogue-card__actions">
        {known.indexed && (
          <button type="button" className="btn btn--primary" onClick={() => desk.searchWithin({ itemId: known.item_id, label })}>
            Search inside this
          </button>
        )}
        {c.pdf_key && (
          <button type="button" className="btn" onClick={() => openPdf({ citation: c, pdf_path: "" }).catch(() => undefined)}>
            Open PDF
          </button>
        )}
        <button type="button" className="btn" onClick={() => showInZotero(c)}>Show in Zotero</button>
      </div>
      {others.length > 0 && (
        <p className="catalogue-card__others">
          Also by that name:{" "}
          {others.map((o, i) => (
            <React.Fragment key={o.item_id}>
              {i > 0 && "; "}
              <button type="button" className="link-button" onClick={() => showInZotero(o.citation)}>
                {o.citation ? `${o.citation.title}` : o.item_id}
              </button>
            </React.Fragment>
          ))}
        </p>
      )}
      <span className="catalogue-card__hole" aria-hidden="true" />
    </section>
  );
};

const Row = React.forwardRef<HTMLButtonElement, { item: DeskItem; selected: boolean; pinned: boolean; onPick: () => void }>(
  ({ item, selected, pinned, onPick }, ref) => {
    const desk = useDesk();
    const best = item.passages[0];
    const meta = [
      itemTypeLabel(item.citation?.item_type || item.item_type),
      `${item.passages.length} passage${item.passages.length === 1 ? "" : "s"}`,
      pageSpan(item.pages),
      item.tags.slice(0, 2).map((t) => (t.length > 28 ? `${t.slice(0, 27)}…` : t)).join(", "),
      item.duplicates?.length ? `stored ${item.duplicates.length + 1}× in Zotero` : "",
    ].filter(Boolean);
    return (
      <li className={selected ? "row row--selected" : "row"}>
        <button type="button" ref={ref} className="row__select" aria-pressed={selected} onClick={onPick} data-item={item.item_id}>
          <span className="row__rank" aria-hidden="true">
            {selected && <span className="row__marker">▸</span>}
            {item.rank}
          </span>
          <span className="row__body">
            <span className="row__ref"><Reference item={item} /></span>
            <span className="row__meta">
              {meta.join(" · ")}
              {pinned && <span className="row__pinned"> · ● pinned</span>}
            </span>
            {item.extract.text && (
              <span className="row__extract">
                “<Highlighted text={item.extract.text} spans={item.extract.highlights} />”
                {item.extract.page && <span className="row__page"> p. {item.extract.page}</span>}
              </span>
            )}
          </span>
          <span className="row__band"><BandMark band={item.band} withLabel /></span>
        </button>
        {selected && (
          <div className="row__actions">
            {(item.citation?.pdf_key || item.pdf_path) && (
              <button type="button" className="btn btn--primary" onClick={() => openPdf(item, best?.page).catch((e) => alert(e.message))}>
                Open PDF{best?.page ? ` p. ${best.page}` : ""}
              </button>
            )}
            {item.citation && <button type="button" className="btn" onClick={() => showInZotero(item.citation)}>Show in Zotero</button>}
            {best && (
              <button type="button" className="btn" onClick={() => desk.togglePin(item, best)}>
                {desk.isPinned(item, best) ? "Unpin passage" : "Pin passage"}
              </button>
            )}
            <button type="button" className="btn" onClick={() => desk.setPane("verify")}>Evidence</button>
          </div>
        )}
      </li>
    );
  },
);
Row.displayName = "Row";

const Bibliography: React.FC<{ indexEmpty: boolean }> = ({ indexEmpty }) => {
  const desk = useDesk();
  const { result, status, error } = desk;
  const [showSeeAlso, setShowSeeAlso] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());

  const sorted = useMemo(() => sortItems(result?.items ?? [], desk.sort), [result, desk.sort]);
  const listed = sorted.filter((it) => it.band !== "see_also");
  const seeAlso = sorted.filter((it) => it.band === "see_also");
  const known = result?.known_items.filter((k) => k.citation) ?? [];
  // A name-and-year query has no topic, so weak passages are expected: the card answers it.
  const nothingStrong = !!result && result.items.length > 0 && listed.length === 0 && known.length === 0;
  const visible = showSeeAlso || nothingStrong ? [...listed, ...seeAlso] : listed;
  const pinnedItems = useMemo(() => new Set(desk.pins.map((p) => p.itemId)), [desk.pins]);

  useEffect(() => setShowSeeAlso(false), [result]);

  function move(delta: number) {
    const index = visible.findIndex((it) => it.item_id === desk.selectedId);
    const next = visible[Math.min(visible.length - 1, Math.max(0, index + delta))];
    if (!next) return;
    desk.select(next.item_id);
    rowRefs.current.get(next.item_id)?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if ((e.target as HTMLElement).closest("input, textarea, select")) return;
    const item = desk.selected;
    if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); move(-1); }
    else if (e.key === "ArrowRight") {
      e.preventDefault();
      desk.setPane("verify");
      document.getElementById("desk-evidence")?.focus();
    } else if (e.key === "p" && item?.passages[0]) { e.preventDefault(); desk.togglePin(item, item.passages[0]); }
    else if (e.key === "o" && item) { e.preventDefault(); openPdf(item, item.passages[0]?.page).catch((err) => alert(err.message)); }
  }

  async function copyBibliography() {
    const text = visible.map((it) => plain(reference(it))).join("\n");
    setCopied((await copyText(text)) ? `Copied ${visible.length} references` : "Could not reach the clipboard");
    window.setTimeout(() => setCopied(null), 2500);
  }

  const renderRow = (item: DeskItem) => (
    <Row
      key={item.item_id}
      ref={(el) => {
        if (el) rowRefs.current.set(item.item_id, el);
        else rowRefs.current.delete(item.item_id);
      }}
      item={item}
      selected={item.item_id === desk.selectedId}
      pinned={pinnedItems.has(item.item_id)}
      onPick={() => {
        desk.select(item.item_id);
        desk.setPane("verify");
      }}
    />
  );

  return (
    <div className="bibliography" onKeyDown={onKeyDown}>
      <div className="panel-head panel-head--page">
        <span className="panel-head__title">
          Bibliography{result ? ` · ${result.items.length} item${result.items.length === 1 ? "" : "s"}` : ""}
        </span>
        {result && result.items.length > 0 && (
          <div className="panel-head__tools">
            <label className="tool">
              <span>Sort</span>
              <select value={desk.sort} onChange={(e) => desk.setSort(e.target.value as Sort)}>
                <option value="relevance">relevance</option>
                <option value="year">year, newest first</option>
                <option value="author">first author</option>
              </select>
            </label>
            <button type="button" className="tool-button" onClick={copyBibliography}>Copy references</button>
          </div>
        )}
      </div>
      <div className="bibliography__status" role="status" aria-live="polite">
        {status === "loading" && <span className="loading-rule">Searching the shelves…</span>}
        {copied}
      </div>

      {status === "error" && (
        <div className="desk-notice desk-notice--error">
          <p>{error}</p>
          <button type="button" className="btn" onClick={() => desk.submit()}>Try again</button>
        </div>
      )}

      {!result && status !== "error" && (
        <div className="desk-intro">
          {indexEmpty ? (
            <>
              <h2>Your library is not indexed yet.</h2>
              <p>The desk searches the full text of your PDFs, so it needs an index first. It is built on this computer and nothing leaves it.</p>
              <button type="button" className="btn btn--primary" onClick={() => desk.setRoom("library")}>Open the library to index it</button>
            </>
          ) : (
            <>
              <h2>Ask the catalogue.</h2>
              <p>Type a topic, a title, or an author and year. The desk returns the items in your library that bear on it, ranked, with the passages that matched. It does not write answers.</p>
              <ul className="desk-intro__examples">
                <li><span className="mono">a topic</span> how platform workers organise</li>
                <li><span className="mono">a title</span> “Cruel optimism”</li>
                <li><span className="mono">a name</span> Woodcock 2020</li>
                <li><span className="mono">a scope</span> courier strikes since 2015</li>
              </ul>
            </>
          )}
        </div>
      )}

      {result && (
        <div className="bibliography__results">
          {result.scope.extracted_ignored && (
            <p className="desk-notice">
              Nothing matched {describeScope(result.scope.extracted)} on this, so that limit was set aside.
            </p>
          )}
          {known[0] && <KnownItemCard known={known[0]} others={known.slice(1)} />}

          {result.items.length === 0 ? (
            <div className="desk-empty">
              <h2>Nothing in your library matches this.</h2>
              <p>Try other words for the same idea, or a wider scope.</p>
              {(Object.keys(desk.scope).length > 0 || desk.within) && (
                <button type="button" className="btn" onClick={() => (desk.within ? desk.searchWithin(null) : desk.setScope({}))}>
                  Search the whole library
                </button>
              )}
            </div>
          ) : (
            <>
              {nothingStrong && (
                <div className="desk-empty desk-empty--slim">
                  <h2>Nothing strong on this in your library.</h2>
                  <p>These are the nearest items the shelves hold.</p>
                </div>
              )}
              <ol className="rows" aria-label="Bibliography">
                {(nothingStrong ? seeAlso : listed).map(renderRow)}
              </ol>
              {seeAlso.length > 0 && !nothingStrong && (
                <>
                  <div className="see-also">
                    <span className="see-also__label">see also</span>
                    <span className="see-also__count">
                      {seeAlso.length} item{seeAlso.length === 1 ? "" : "s"} with only weak matches
                    </span>
                    <button type="button" className="btn" aria-expanded={showSeeAlso} onClick={() => setShowSeeAlso((v) => !v)}>
                      {showSeeAlso ? "Hide" : "Show"}
                    </button>
                  </div>
                  {showSeeAlso && (
                    <ol className="rows rows--see-also" aria-label="See also">
                      {seeAlso.map(renderRow)}
                    </ol>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default Bibliography;
