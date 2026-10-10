import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { search } from "../../api/search";
import { useProfile } from "../../contexts/ProfileContext";
import type { DeskItem, Passage, ScopeFilters, SearchResponse } from "../../types/desk";
import { shortCite } from "./cite";

export type Sort = "relevance" | "year" | "author";
export type Room = "desk" | "library" | "about";

/** A passage the reader kept: the reading list. */
export interface Pin {
  id: string;
  itemId: string;
  label: string;
  page: number | null;
  text: string;
  query: string;
  at: number;
}

/** One row of the query log: the trail of a search session (Bates' berrypicking). */
export interface LogEntry {
  query: string;
  scope: ScopeFilters;
  count: number;
  at: number;
}

type Status = "idle" | "loading" | "error";

/** Which pane is in front on narrow windows: Ask, Browse or Verify. */
export type Pane = "ask" | "browse" | "verify";

/** Searching inside one item, from a known-item card. */
export interface Within {
  itemId: string;
  label: string;
}

interface DeskState {
  room: Room;
  setRoom: (room: Room) => void;
  query: string;
  setQuery: (q: string) => void;
  scope: ScopeFilters;
  within: Within | null;
  searchWithin: (within: Within | null) => void;
  pane: Pane;
  setPane: (pane: Pane) => void;
  useExtracted: boolean;
  result: SearchResponse | null;
  status: Status;
  error: string | null;
  selectedId: string | null;
  select: (itemId: string | null) => void;
  selected: DeskItem | null;
  sort: Sort;
  setSort: (s: Sort) => void;
  pins: Pin[];
  log: LogEntry[];
  submit: (query?: string) => void;
  setScope: (scope: ScopeFilters) => void;
  dropExtracted: (key: keyof ScopeFilters, value?: string) => void;
  restore: (entry: LogEntry) => void;
  forget: (entry: LogEntry) => void;
  togglePin: (item: DeskItem, passage: Passage) => void;
  isPinned: (item: DeskItem, passage: Passage) => boolean;
  clearPins: () => void;
}

const DeskContext = createContext<DeskState | null>(null);

const LOG_LIMIT = 50;

function pinId(itemId: string, passage: Passage): string {
  return `${itemId}:${passage.page ?? ""}:${passage.text.slice(0, 48)}`;
}

function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

/**
 * State kept per profile in localStorage.
 * shortcut: browser storage, so pins and the log stay on this machine and are
 * lost if site data is cleared; move to a per-profile backend file (roadmap Stage 3).
 */
function useStoredState<T>(key: string, fallback: T): [T, (update: (prev: T) => T) => void] {
  const [state, setState] = useState(() => ({ key, value: readStored(key, fallback) }));
  let current = state;
  if (state.key !== key) {
    // The profile changed: load its own value instead of carrying the old one over.
    current = { key, value: readStored(key, fallback) };
    setState(current);
  }
  const update = useCallback((fn: (prev: T) => T) => {
    setState((prev) => {
      const next = { key: prev.key, value: fn(prev.value) };
      try {
        localStorage.setItem(prev.key, JSON.stringify(next.value));
      } catch {
        // Storage full or blocked: keep the in-memory value for this session.
      }
      return next;
    });
  }, []);
  return [current.value, update];
}

function sameScope(a: ScopeFilters, b: ScopeFilters): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Remove one value (or a whole key) from a scope, dropping keys left empty. */
export function withoutScope(scope: ScopeFilters, key: keyof ScopeFilters, value?: string): ScopeFilters {
  const next: ScopeFilters = { ...scope };
  const current = next[key];
  if (Array.isArray(current) && value !== undefined) {
    const rest = current.filter((v) => v !== value);
    if (rest.length) (next as Record<string, unknown>)[key] = rest;
    else delete next[key];
  } else {
    delete next[key];
  }
  return next;
}

/** Merge scope b into a, list values unioned. */
export function mergeScope(a: ScopeFilters, b: ScopeFilters): ScopeFilters {
  const out: ScopeFilters = { ...a };
  for (const [key, value] of Object.entries(b) as [keyof ScopeFilters, unknown][]) {
    if (Array.isArray(value)) {
      const prev = (out[key] as string[] | undefined) ?? [];
      (out as Record<string, unknown>)[key] = Array.from(new Set([...prev, ...value]));
    } else if (value !== undefined && value !== null && value !== "") {
      (out as Record<string, unknown>)[key] = value;
    }
  }
  return out;
}

export const DeskProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const { activeProfileId } = useProfile();
  const prefix = `desk:${activeProfileId || "default"}`;

  const [room, setRoom] = useState<Room>("desk");
  const [query, setQuery] = useState("");
  const [scope, setScopeState] = useState<ScopeFilters>({});
  const [within, setWithin] = useState<Within | null>(null);
  const [pane, setPane] = useState<Pane>("ask");
  const [useExtracted, setUseExtracted] = useState(true);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("relevance");
  const [pins, setPins] = useStoredState<Pin[]>(`${prefix}:pins`, []);
  const [log, setLog] = useStoredState<LogEntry[]>(`${prefix}:log`, []);
  const inflight = useRef<AbortController | null>(null);

  const run = useCallback(
    async (text: string, nextScope: ScopeFilters, extracted: boolean, inside: Within | null) => {
      const q = text.trim();
      if (!q) return;
      inflight.current?.abort();
      const controller = new AbortController();
      inflight.current = controller;
      setStatus("loading");
      setError(null);
      try {
        const res = await search(
          {
            query: q,
            manual_filters: nextScope,
            use_metadata_filters: extracted,
            item_ids: inside ? [inside.itemId] : undefined,
          },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setResult(res);
        setStatus("idle");
        setPane("browse");
        setSelectedId((prev) =>
          prev && res.items.some((it) => it.item_id === prev)
            ? prev
            : res.items.find((it) => it.band !== "see_also")?.item_id ?? null,
        );
        // One log row per query text: a scope change updates the row instead of adding one.
        setLog((prev) =>
          [
            { query: q, scope: nextScope, count: res.items.length, at: Date.now() },
            ...prev.filter((e) => e.query.toLocaleLowerCase() !== q.toLocaleLowerCase()),
          ].slice(0, LOG_LIMIT),
        );
      } catch (e) {
        if (controller.signal.aborted) return;
        setStatus("error");
        setError(e instanceof Error ? e.message : "The search failed.");
      }
    },
    [setLog],
  );

  const submit = useCallback(
    (text?: string) => {
      const q = text ?? query;
      if (text !== undefined) setQuery(text);
      setUseExtracted(true);
      void run(q, scope, true, within);
    },
    [query, scope, within, run],
  );

  const setScope = useCallback(
    (next: ScopeFilters) => {
      setScopeState(next);
      if (result) void run(query || result.query, next, useExtracted, within);
    },
    [result, query, useExtracted, within, run],
  );

  /**
   * Remove a chip that was read from the query. Extraction is switched off for
   * this query and the other extracted values become ordinary scope, so the
   * reader sees exactly what is applied.
   */
  const dropExtracted = useCallback(
    (key: keyof ScopeFilters, value?: string) => {
      const extracted = result?.scope.extracted ?? {};
      const next = mergeScope(scope, withoutScope(extracted, key, value));
      setScopeState(next);
      setUseExtracted(false);
      void run(query || result?.query || "", next, false, within);
    },
    [result, scope, query, within, run],
  );

  const restore = useCallback(
    (entry: LogEntry) => {
      setQuery(entry.query);
      setScopeState(entry.scope);
      setUseExtracted(true);
      setWithin(null);
      setRoom("desk");
      void run(entry.query, entry.scope, true, null);
    },
    [run],
  );

  const forget = useCallback(
    (entry: LogEntry) => setLog((prev) => prev.filter((e) => !(e.query === entry.query && sameScope(e.scope, entry.scope)))),
    [setLog],
  );

  const togglePin = useCallback(
    (item: DeskItem, passage: Passage) => {
      const id = pinId(item.item_id, passage);
      setPins((prev) =>
        prev.some((p) => p.id === id)
          ? prev.filter((p) => p.id !== id)
          : [
              ...prev,
              {
                id,
                itemId: item.item_id,
                label: shortCite(item),
                page: passage.page,
                text: passage.text,
                query: result?.query ?? query,
                at: Date.now(),
              },
            ],
      );
    },
    [setPins, result, query],
  );

  /**
   * Scope the next search to one item. Clearing it re-runs the current query
   * across the whole library; setting it empties the query field so the reader
   * types what to look for inside the item.
   */
  const searchWithin = useCallback(
    (next: Within | null) => {
      setWithin(next);
      setRoom("desk");
      if (next) {
        setQuery("");
        setPane("ask");
        window.dispatchEvent(new Event("desk:focus-query"));
      } else if (result) {
        void run(query || result.query, scope, useExtracted, null);
      }
    },
    [result, query, scope, useExtracted, run],
  );

  const pinIds = useMemo(() => new Set(pins.map((p) => p.id)), [pins]);
  const isPinned = useCallback(
    (item: DeskItem, passage: Passage) => pinIds.has(pinId(item.item_id, passage)),
    [pinIds],
  );
  const clearPins = useCallback(() => setPins(() => []), [setPins]);

  const selected = useMemo(
    () => result?.items.find((it) => it.item_id === selectedId) ?? null,
    [result, selectedId],
  );

  const value: DeskState = {
    room, setRoom, query, setQuery, scope, within, searchWithin, pane, setPane, useExtracted, result, status, error,
    selectedId, select: setSelectedId, selected, sort, setSort, pins, log,
    submit, setScope, dropExtracted, restore, forget, togglePin, isPinned, clearPins,
  };
  return <DeskContext.Provider value={value}>{children}</DeskContext.Provider>;
};

export function useDesk(): DeskState {
  const ctx = useContext(DeskContext);
  if (!ctx) throw new Error("useDesk must be used within a DeskProvider");
  return ctx;
}
