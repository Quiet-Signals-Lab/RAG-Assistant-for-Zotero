import React, { useEffect, useMemo, useRef, useState } from "react";
import type { Citation, DeskItem, KnownItem, ScopeFilters } from "../../types/desk";
import { plain, reference, shortCite, sortName } from "./cite";
import { useDesk, type Sort } from "./DeskContext";
import { bibtex, pathfinder, ris } from "./exports";
import { formatReferences } from "./csl";
import { BUNDLED_STYLES, LOCALE_EN_US } from "./styles";
import { apiFetch, request } from "../../api/client";
import { FACETS, groupBy, refinements, type Facet, type Refinement } from "./facets";
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

/** Save text as a file; Electron asks where. */
function saveFile(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function fileStem(query: string): string {
  return query.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "").slice(0, 48) || "references";
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

type RowProps = { item: DeskItem; selected: boolean; pinned: boolean; onPick: () => void };

const Row = React.forwardRef<HTMLButtonElement, RowProps>(
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
            <button type="button" className="btn" onClick={() => desk.moreLike(item)}>More like this</button>
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
  const [facet, setFacet] = useState<Facet>("none");
  const [copied, setCopied] = useState<string | null>(null);
  const [style, setStyle] = useState<string>(() => { try { return localStorage.getItem("desk.cslStyle") || "apa"; } catch { return "apa"; } });
  const [zoteroStyles, setZoteroStyles] = useState<{ file: string; title: string }[]>([]);
  useEffect(() => {
    request<{ styles: { file: string; title: string }[] }>("/api/csl/styles").then((r) => setZoteroStyles(r.styles)).catch(() => setZoteroStyles([]));
  }, []);

  /** The visible list in the chosen CSL style: a bundled one, or one installed in Zotero. */
  async function references(): Promise<string> {
    const bundled = BUNDLED_STYLES.find((s) => s.id === style);
    const xml = bundled ? bundled.xml : await apiFetch(`/api/csl/styles/${encodeURIComponent(style.replace(/^zotero:/, ""))}`).then((r) => r.text());
    return formatReferences(visible, xml, LOCALE_EN_US).join("\n");
  }
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());

  const sorted = useMemo(() => sortItems(result?.items ?? [], desk.sort), [result, desk.sort]);
  const ranked = useMemo(() => sorted.filter((it) => it.band !== "see_also"), [sorted]);
  const groups = useMemo(() => groupBy(ranked, facet, desk.clerk.themes), [ranked, facet, desk.clerk.themes]);
  const listed = groups ? groups.flatMap((g) => g.items) : ranked;
  const seeAlso = sorted.filter((it) => it.band === "see_also");
  const known = result?.known_items.filter((k) => k.citation) ?? [];
  // A name-and-year query has no topic, so weak passages are expected: the card answers it.
  const nothingStrong = !!result && result.items.length > 0 && listed.length === 0 && known.length === 0;
  // A topical phrase scores lower with the reranker than a question does, so the items it
  // ranked first can all sit just under the "see also" line: with fewer than three listed,
  // the nearest items are shown rather than folded away behind one row.
  const fewListed = listed.length > 0 && listed.length < 3 && seeAlso.length > 0 && known.length === 0;
  const seeAlsoOpen = showSeeAlso || fewListed;
  const visible = seeAlsoOpen || nothingStrong ? [...listed, ...seeAlso] : listed;
  const refine = useMemo(() => (result && !desk.within ? refinements(ranked, desk.scope) : []), [result, ranked, desk.scope, desk.within]);
  const applyRefinement = (r: Refinement) => {
    if (r.kind === "decade") desk.setScope({ ...desk.scope, year_min: r.year_min, year_max: r.year_max });
    else if (r.kind === "collection") desk.setScope({ ...desk.scope, collections: [...(desk.scope.collections ?? []), r.collection] });
    else desk.putAside(r.item_ids);
  };
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

  function saveAs(format: string) {
    const stem = fileStem(result?.query ?? "");
    if (format === "txt") references().then((text) => saveFile(`${stem}.txt`, text, "text/plain")).catch(() => setCopied("This style could not be read"));
    else if (format === "bib") saveFile(`${stem}.bib`, bibtex(visible), "application/x-bibtex");
    else if (format === "ris") saveFile(`${stem}.ris`, ris(visible), "application/x-research-info-systems");
    else if (format === "pathfinder" && result) {
      const text = pathfinder({
        query: result.query,
        scope: describeScope({ ...result.scope.extracted, ...desk.scope }).replace("that limit", ""),
        date: new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }),
        // The groups on screen, else the model's themes, else one list.
        groups: groups ?? groupBy(ranked, "theme", desk.clerk.themes) ?? [{ label: "Results", items: ranked }],
        pins: desk.pins.filter((pin) => result.items.some((it) => it.item_id === pin.itemId)),
      });
      saveFile(`reading-guide-${stem}.md`, text, "text/markdown");
    }
  }

  async function copyBibliography() {
    let note: string;
    try {
      note = (await copyText(await references())) ? `Copied ${visible.length} references` : "Could not reach the clipboard";
    } catch {
      note = "This style could not be read";
    }
    setCopied(note);
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
        <h2 className="panel-head__title">
          Results{result ? ` · ${result.items.length} item${result.items.length === 1 ? "" : "s"}` : ""}
        </h2>
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
            <label className="tool">
              <span>Group</span>
              <select value={facet} onChange={(e) => setFacet(e.target.value as Facet)}>
                {FACETS.filter((f) => f.id !== "theme" || desk.clerk.themes).map((f) => (
                  <option key={f.id} value={f.id}>{f.label}</option>
                ))}
              </select>
            </label>
            <label className="tool">
              <span>Style</span>
              <select value={style} onChange={(e) => { setStyle(e.target.value); try { localStorage.setItem("desk.cslStyle", e.target.value); } catch { /* per-viewer convenience only */ } }}>
                {BUNDLED_STYLES.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
                {zoteroStyles.length > 0 && (
                  <optgroup label="Installed in Zotero">
                    {zoteroStyles.map((s) => <option key={s.file} value={`zotero:${s.file}`}>{s.title}</option>)}
                  </optgroup>
                )}
              </select>
            </label>
            <button type="button" className="tool-button" onClick={copyBibliography}>Copy references</button>
            <label className="tool">
              <span className="sr-only">Save the list as</span>
              <select value="" onChange={(e) => saveAs(e.target.value)} aria-label="Save the list as a file">
                <option value="" disabled>Save as…</option>
                <option value="txt">References in this style (.txt)</option>
                <option value="bib">BibTeX (.bib)</option>
                <option value="ris">RIS (.ris)</option>
                <option value="pathfinder">Reading guide (.md)</option>
              </select>
            </label>
          </div>
        )}
      </div>
      <div className="bibliography__status" role="status" aria-live="polite">
        {status === "loading" && <span className="loading-rule">Searching…</span>}
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
              <p>Search covers the full text of your PDFs, so it needs an index first. The index is built on this computer and nothing leaves it.</p>
              <button type="button" className="btn btn--primary" onClick={() => desk.setRoom("library")}>Open the library to index it</button>
            </>
          ) : (
            <>
              <h2>Search your library.</h2>
              <p>Type a topic, a title, or an author and year. You get the items in your library that bear on it, ranked, with the passages that matched. No answer is written for you.</p>
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
          {refine.length > 0 && (
            <div className="refine" aria-label="Narrow the list">
              <span className="refine__label">Narrow</span>
              {refine.map((r) => (
                <button key={r.kind} type="button" className="chip chip--suggest" onClick={() => applyRefinement(r)}>
                  {r.label}
                  {r.kind !== "set_aside" && <span className="chip__note"> · {r.count}</span>}
                </button>
              ))}
            </div>
          )}

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
                  <p>These are the nearest items your library holds.</p>
                </div>
              )}
              {groups && !nothingStrong ? (
                groups.map((g, i) => (
                  <section key={`${i}-${g.label}`} className="rows__group" aria-label={`Group: ${g.label}`}>
                    <h3 className="rows__group-head">
                      <span>{g.label}</span>
                      <span className="rows__group-count">{g.items.length}</span>
                    </h3>
                    <ol className="rows">{g.items.map(renderRow)}</ol>
                  </section>
                ))
              ) : (
                <ol className="rows" aria-label="Bibliography">
                  {(nothingStrong ? seeAlso : listed).map(renderRow)}
                </ol>
              )}
              {seeAlso.length > 0 && !nothingStrong && (
                <>
                  <div className="see-also">
                    <span className="see-also__label">see also</span>
                    <span className="see-also__count">
                      {seeAlso.length} item{seeAlso.length === 1 ? "" : "s"} with only weak matches
                      {fewListed ? ", shown since little else matched" : ""}
                    </span>
                    {!fewListed && (
                      <button type="button" className="btn" aria-expanded={showSeeAlso} onClick={() => setShowSeeAlso((v) => !v)}>
                        {showSeeAlso ? "Hide" : "Show"}
                      </button>
                    )}
                  </div>
                  {seeAlsoOpen && (
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
