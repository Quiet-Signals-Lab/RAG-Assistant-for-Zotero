import React, { useEffect, useId, useRef, useState } from "react";
import { request } from "../../api/client";
import type { Relation, ScopeFilters } from "../../types/desk";
import { itemTypeLabel } from "./cite";
import { useDesk, withoutScope } from "./DeskContext";

type Vocabulary = { tags: string[]; collections: string[]; itemTypes: string[] };

/** Tags, collections and item types in the library, for the scope editor. Loaded once, on demand. */
function useVocabulary(open: boolean): Vocabulary {
  const [vocab, setVocab] = useState<Vocabulary>({ tags: [], collections: [], itemTypes: [] });
  const loaded = useRef(false);
  useEffect(() => {
    if (!open || loaded.current) return;
    loaded.current = true;
    Promise.allSettled([
      request<{ tags: string[] }>("/api/library/tags"),
      request<{ collections: { name: string }[] }>("/api/library/collections"),
      request<{ item_types: { name: string }[] }>("/api/library/item_types"),
    ]).then(([tags, collections, types]) => {
      setVocab({
        tags: tags.status === "fulfilled" ? tags.value.tags : [],
        collections: collections.status === "fulfilled" ? collections.value.collections.map((c) => c.name) : [],
        itemTypes: types.status === "fulfilled" ? types.value.item_types.map((t) => t.name) : [],
      });
    });
  }, [open]);
  return vocab;
}

type Chip = { key: keyof ScopeFilters; value?: string; label: string };

function chipsFor(scope: ScopeFilters): Chip[] {
  const chips: Chip[] = [];
  const { year_min: lo, year_max: hi } = scope;
  if (lo && hi) chips.push({ key: "year_min", label: `${lo}–${hi}` });
  else if (lo) chips.push({ key: "year_min", label: `since ${lo}` });
  else if (hi) chips.push({ key: "year_max", label: `until ${hi}` });
  scope.tags?.forEach((t) => chips.push({ key: "tags", value: t, label: `tag ${t}` }));
  scope.collections?.forEach((c) => chips.push({ key: "collections", value: c, label: `in ${c}` }));
  scope.item_types?.forEach((t) => chips.push({ key: "item_types", value: t, label: itemTypeLabel(t) }));
  if (scope.author) chips.push({ key: "author", label: `by ${scope.author}` });
  if (scope.title) chips.push({ key: "title", label: `title “${scope.title}”` });
  scope.exclude?.forEach((x) => chips.push({ key: "exclude", value: x, label: `not ${x}` }));
  return chips;
}

/** A year chip covers both ends of a range, so removing it removes both. */
function removeChip(scope: ScopeFilters, chip: Chip): ScopeFilters {
  if (chip.key === "year_min" && scope.year_max && scope.year_min) {
    return withoutScope(withoutScope(scope, "year_min"), "year_max");
  }
  return withoutScope(scope, chip.key, chip.value);
}

/** ISO 25964's thesaurus relations, as a catalogue card prints them. */
const RELATION: Record<Relation, { abbr: string; title: string }> = {
  broader: { abbr: "broader", title: "A broader subject" },
  narrower: { abbr: "narrower", title: "A narrower subject" },
  related: { abbr: "related", title: "A related subject" },
};

const ScopeEditor: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const desk = useDesk();
  const vocab = useVocabulary(true);
  const id = useId();
  const [from, setFrom] = useState(desk.scope.year_min ? String(desk.scope.year_min) : "");
  const [to, setTo] = useState(desk.scope.year_max ? String(desk.scope.year_max) : "");
  const [tag, setTag] = useState("");
  const [collection, setCollection] = useState("");
  const [itemType, setItemType] = useState("");
  const [author, setAuthor] = useState(desk.scope.author ?? "");

  function apply(e: React.FormEvent) {
    e.preventDefault();
    const next: ScopeFilters = { ...desk.scope };
    const year = (v: string) => (/^\d{4}$/.test(v.trim()) ? parseInt(v, 10) : undefined);
    next.year_min = year(from);
    next.year_max = year(to);
    if (!next.year_min) delete next.year_min;
    if (!next.year_max) delete next.year_max;
    const add = (key: "tags" | "collections" | "item_types", value: string) => {
      if (value.trim()) next[key] = Array.from(new Set([...(next[key] ?? []), value.trim()]));
    };
    add("tags", tag);
    add("collections", collection);
    add("item_types", itemType);
    if (author.trim()) next.author = author.trim();
    else delete next.author;
    desk.setScope(next);
    onClose();
  }

  return (
    <form className="scope-editor" onSubmit={apply} aria-label="Edit limits">
      <div className="scope-editor__years">
        <label htmlFor={`${id}-from`}>From</label>
        <input id={`${id}-from`} inputMode="numeric" placeholder="1995" value={from} onChange={(e) => setFrom(e.target.value)} />
        <label htmlFor={`${id}-to`}>to</label>
        <input id={`${id}-to`} inputMode="numeric" placeholder="2026" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <label htmlFor={`${id}-tag`}>Tag</label>
      <input id={`${id}-tag`} list={`${id}-tags`} value={tag} onChange={(e) => setTag(e.target.value)} placeholder="Any tag" />
      <datalist id={`${id}-tags`}>{vocab.tags.map((t) => <option key={t} value={t} />)}</datalist>
      <label htmlFor={`${id}-coll`}>Collection</label>
      <select id={`${id}-coll`} value={collection} onChange={(e) => setCollection(e.target.value)}>
        <option value="">Any collection</option>
        {vocab.collections.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <label htmlFor={`${id}-type`}>Item type</label>
      <select id={`${id}-type`} value={itemType} onChange={(e) => setItemType(e.target.value)}>
        <option value="">Any type</option>
        {vocab.itemTypes.map((t) => <option key={t} value={t}>{itemTypeLabel(t)}</option>)}
      </select>
      <label htmlFor={`${id}-author`}>Author</label>
      <input id={`${id}-author`} value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Last name" />
      <div className="scope-editor__actions">
        <button type="submit" className="btn btn--primary">Apply</button>
        <button type="button" className="btn" onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
};

const QueryDesk: React.FC = () => {
  const desk = useDesk();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    const focus = () => {
      inputRef.current?.focus();
      inputRef.current?.select();
    };
    // "/" jumps to the query from anywhere that is not a text field.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.target as HTMLElement).closest("input, textarea, select, [contenteditable='true']")) return;
      e.preventDefault();
      desk.setPane("ask");
      focus();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("desk:focus-query", focus);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("desk:focus-query", focus);
    };
  }, [desk.setPane]); // eslint-disable-line react-hooks/exhaustive-deps

  const manual = chipsFor(desk.scope);
  // When the read limits found nothing and were set aside, exclusions still applied: keep showing them.
  const readScope = desk.result?.scope;
  const extracted = desk.useExtracted && readScope
    ? chipsFor(readScope.extracted_ignored ? { exclude: readScope.extracted.exclude } : readScope.extracted)
    : [];
  const current = desk.result?.query.toLocaleLowerCase();
  const scopeRead = desk.result?.scope;
  const topicDiffers = !!scopeRead?.topic && scopeRead.topic.toLocaleLowerCase() !== current;

  return (
    <div className="query-desk">
      <form
        role="search"
        className="query-desk__form"
        onSubmit={(e) => {
          e.preventDefault();
          desk.submit();
        }}
      >
        <div className="panel-head">
          <h2 className="panel-head__title">Search</h2>
          <span className="panel-head__hint" aria-hidden="true">/ to return here</span>
        </div>
        <label htmlFor="desk-query" className="desk-label">What are you looking for</label>
        <textarea
          id="desk-query"
          ref={inputRef}
          className="query-desk__input"
          value={desk.query}
          rows={2}
          onChange={(e) => desk.setQuery(e.target.value)}
          onKeyDown={(e) => {
            // Enter searches; Shift+Enter starts a new line in a long query.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (desk.query.trim() && desk.status !== "loading") desk.submit();
            }
          }}
          placeholder={desk.within ? "What to look for inside it" : "A topic, a title, or an author and year"}
          autoComplete="off"
          spellCheck={false}
        />
        <button type="submit" className="btn btn--primary query-desk__go" disabled={!desk.query.trim() || desk.status === "loading"}>
          {desk.status === "loading" ? "Searching…" : "Search"}
        </button>
      </form>

      {topicDiffers && extracted.length > 0 && (
        <p className="query-desk__reading">
          Searched for <q>{scopeRead?.topic}</q>
          <span className="query-desk__reader">
            {scopeRead?.read_by === "model" ? " · limits read by the language model" : " · limits read from your words"}
          </span>
        </p>
      )}

      <section className="query-desk__section" aria-labelledby="scope-heading">
        <h2 id="scope-heading" className="desk-label">Limits</h2>
        <div className="chips">
          {desk.within && (
            <button type="button" className="chip chip--on" onClick={() => desk.searchWithin(null)} title="Search the whole library again">
              within {desk.within.label} <span aria-hidden="true">×</span>
              <span className="sr-only">, remove</span>
            </button>
          )}
          {desk.setAside.length > 0 && (
            <button type="button" className="chip chip--on" onClick={() => desk.putAside(null)} title="Bring them back into the list">
              {desk.setAside.length} item{desk.setAside.length === 1 ? "" : "s"} set aside <span aria-hidden="true">×</span>
              <span className="sr-only">, bring back</span>
            </button>
          )}
          {manual.map((chip) => (
            <button
              type="button"
              key={`m-${chip.key}-${chip.value ?? ""}`}
              className="chip chip--on"
              onClick={() => desk.setScope(removeChip(desk.scope, chip))}
            >
              {chip.label} <span aria-hidden="true">×</span>
              <span className="sr-only">, remove</span>
            </button>
          ))}
          {extracted.map((chip) => (
            <button
              type="button"
              key={`x-${chip.key}-${chip.value ?? ""}`}
              className="chip chip--read"
              title="Read from your query. Remove it if that is not what you meant."
              onClick={() => desk.dropExtracted(chip.key, chip.value)}
            >
              {chip.label} <span className="chip__note">· read</span> <span aria-hidden="true">×</span>
              <span className="sr-only">, read from the query, remove</span>
            </button>
          ))}
          <button type="button" className="chip chip--add" aria-expanded={editing} onClick={() => setEditing((v) => !v)}>
            + add a limit
          </button>
        </div>
        {editing && <ScopeEditor onClose={() => setEditing(false)} />}
      </section>

      {desk.clerk.alsoTry && desk.clerk.alsoTry.length > 0 && (
        <section className="query-desk__section" aria-labelledby="also-heading">
          <h2 id="also-heading" className="desk-label desk-label--split">
            <span>Related searches</span>
            <span className="desk-label__aside">from your library</span>
          </h2>
          <ul className="also-try">
            {desk.clerk.alsoTry.map((s) => (
              <li key={s.term}>
                <button type="button" className="also-try__term" onClick={() => desk.submit(s.term)}>
                  <abbr className="also-try__rel" title={RELATION[s.relation].title}>{RELATION[s.relation].abbr}</abbr>
                  <span>{s.term}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="query-desk__section" aria-labelledby="log-heading">
        <h2 id="log-heading" className="desk-label desk-label--split">
          <span>Recent searches</span>
          {desk.log.length > 0 && <span className="desk-label__aside">{desk.log.length}</span>}
        </h2>
        {desk.log.length === 0 ? (
          <p className="query-desk__empty">Your searches collect here, so you can retrace the trail.</p>
        ) : (
          <ul className="log">
            {desk.log.map((entry) => {
              const isCurrent = entry.query.toLocaleLowerCase() === current;
              return (
                <li key={`${entry.query}-${entry.at}`} className={isCurrent ? "log__row log__row--current" : "log__row"}>
                  <button type="button" className="log__open" onClick={() => desk.restore(entry)} aria-current={isCurrent || undefined}>
                    <span className="log__marker" aria-hidden="true">{isCurrent ? "▸" : ""}</span>
                    <span className="log__query">{entry.query}</span>
                    <span className="log__count">{entry.count}</span>
                  </button>
                  <button type="button" className="log__forget" onClick={() => desk.forget(entry)} aria-label={`Remove “${entry.query}” from the log`}>
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
};

export default QueryDesk;
