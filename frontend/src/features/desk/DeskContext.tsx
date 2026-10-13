import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { request } from "../../api/client";
import { annotate, search } from "../../api/search";
import { useProfile } from "../../contexts/ProfileContext";
import type { DeskItem, Passage, ScopeFilters, SearchResponse, Suggestion, Theme } from "../../types/desk";
import { shortCite } from "./cite";

export type Sort = "relevance" | "year" | "author";
export type Room = "desk" | "library" | "clerk" | "about";

/** The clerk's work on the current results; empty until it arrives, and with no model. */
export interface ClerkWork {
  alsoTry: Suggestion[] | null;
  themes: Theme[] | null;
  working: boolean;
}

const NO_CLERK_WORK: ClerkWork = { alsoTry: null, themes: null, working: false };

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
  /** Items left out of this search; cleared by a new query. */
  setAside: string[];
  /** Search with these items left out too, keeping query and scope; null brings them all back. */
  putAside: (itemIds: string[] | null) => void;
  /** Pearl growing: search on an item's title, with the item itself set aside. */
  moreLike: (item: DeskItem) => void;
  pane: Pane;
  setPane: (pane: Pane) => void;
  useExtracted: boolean;
  result: SearchResponse | null;
  clerk: ClerkWork;
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

type DeskFile = { pins: Pin[]; log: LogEntry[] };
type FileState = { profile: string; status: "loading" | "ready" | "failed"; file: DeskFile };

const EMPTY_FILE: DeskFile = { pins: [], log: [] };
const LOAD_RETRIES = [1000, 3000, 8000, 20000];

/** Edits made while the file was loading, laid over what loaded. */
function mergeDesk(loaded: DeskFile, edits: DeskFile): DeskFile {
  const ids = new Set(loaded.pins.map((p) => p.id));
  const queries = new Set(edits.log.map((e) => e.query.toLocaleLowerCase()));
  return {
    pins: [...loaded.pins, ...edits.pins.filter((p) => !ids.has(p.id))],
    log: [...edits.log, ...loaded.log.filter((e) => !queries.has(e.query.toLocaleLowerCase()))].slice(0, LOG_LIMIT),
  };
}

function deskPath(profileId: string): string {
  return `/api/profiles/${encodeURIComponent(profileId)}/desk`;
}

function forgetLegacy(profileId: string): void {
  try {
    localStorage.removeItem(`desk:${profileId}:pins`);
    localStorage.removeItem(`desk:${profileId}:log`);
  } catch {
    // storage blocked: nothing to clean up
  }
}

/**
 * Pins and the query log, kept per profile in desk.json on the backend
 * (GET/PUT /api/profiles/{id}/desk). Earlier versions kept them in browser
 * storage; those are moved into the file the first time a profile loads empty.
 *
 * Nothing is written until the file has loaded: a failed load is retried, never
 * followed by a save that would replace the reader's pins with an empty list.
 */
function useDeskFile(profileId: string): [DeskFile, (update: (prev: DeskFile) => DeskFile) => void] {
  const [state, setState] = useState<FileState>({ profile: profileId, status: "loading", file: EMPTY_FILE });
  // Unsaved changes are edits.current > saved.current; counting avoids losing an
  // edit made while an older save was in flight.
  const edits = useRef(0);
  const saved = useRef(0);
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  }, [state]);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    setState((prev) => (prev.profile === profileId ? prev : { profile: profileId, status: "loading", file: EMPTY_FILE }));

    const load = (attempt: number) => {
      request<DeskFile>(deskPath(profileId))
        .then((loaded) => {
          if (cancelled) return;
          const legacy = { pins: readStored<Pin[]>(`desk:${profileId}:pins`, []), log: readStored<LogEntry[]>(`desk:${profileId}:log`, []) };
          const migrate = !loaded.pins.length && !loaded.log.length && (legacy.pins.length > 0 || legacy.log.length > 0);
          if (migrate) edits.current += 1;
          const base = migrate ? legacy : loaded;
          setState((prev) => ({
            profile: profileId,
            status: "ready",
            file: edits.current > saved.current && prev.profile === profileId ? mergeDesk(base, prev.file) : base,
          }));
        })
        .catch(() => {
          if (cancelled) return;
          if (attempt < LOAD_RETRIES.length) timer = window.setTimeout(() => load(attempt + 1), LOAD_RETRIES[attempt]);
          else setState((prev) => ({ ...prev, profile: profileId, status: "failed" }));
        });
    };
    load(0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      // Leaving this profile: write its pending changes now rather than drop them.
      const last = latest.current;
      if (edits.current > saved.current && last.profile === profileId && last.status === "ready") {
        request(deskPath(profileId), { method: "PUT", body: JSON.stringify(last.file) }).catch(() => undefined);
      }
      edits.current = 0;
      saved.current = 0;
    };
  }, [profileId]);

  // Save shortly after the last change; a failed save keeps the in-memory state and retries on the next edit.
  useEffect(() => {
    if (state.status !== "ready" || state.profile !== profileId || edits.current <= saved.current) return;
    const version = edits.current;
    const timer = window.setTimeout(() => {
      request(deskPath(profileId), { method: "PUT", body: JSON.stringify(state.file) })
        .then(() => {
          saved.current = Math.max(saved.current, version);
          forgetLegacy(profileId);
        })
        .catch(() => undefined);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [state, profileId]);

  const update = useCallback((fn: (prev: DeskFile) => DeskFile) => {
    edits.current += 1;
    setState((prev) => ({ ...prev, file: fn(prev.file) }));
  }, []);
  return [state.profile === profileId ? state.file : EMPTY_FILE, update];
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

  const [room, setRoom] = useState<Room>("desk");
  const [query, setQuery] = useState("");
  const [scope, setScopeState] = useState<ScopeFilters>({});
  const [within, setWithin] = useState<Within | null>(null);
  const [setAside, setSetAside] = useState<string[]>([]);
  const [pane, setPane] = useState<Pane>("ask");
  const [useExtracted, setUseExtracted] = useState(true);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("relevance");
  const [deskFile, updateDeskFile] = useDeskFile(activeProfileId || "default");
  const { pins, log } = deskFile;
  const setPins = useCallback(
    (fn: (prev: Pin[]) => Pin[]) => updateDeskFile((prev) => ({ ...prev, pins: fn(prev.pins) })),
    [updateDeskFile],
  );
  const setLog = useCallback(
    (fn: (prev: LogEntry[]) => LogEntry[]) => updateDeskFile((prev) => ({ ...prev, log: fn(prev.log) })),
    [updateDeskFile],
  );
  const [clerk, setClerk] = useState<ClerkWork>(NO_CLERK_WORK);
  const inflight = useRef<AbortController | null>(null);
  const annotating = useRef<AbortController | null>(null);

  /** Ask the clerk for notes, next searches and themes; each lands as it is ready. */
  const startClerk = useCallback((res: SearchResponse) => {
    const controller = new AbortController();
    annotating.current = controller;
    const items = res.items.map((it) => ({
      item_id: it.item_id,
      title: it.title,
      tags: it.tags,
      band: it.band,
      passages: it.passages.map((p) => ({ page: p.page, text: p.text })),
    }));
    if (!items.length) return;
    setClerk({ ...NO_CLERK_WORK, working: true });
    const apply = (update: (prev: ClerkWork) => ClerkWork) => {
      if (!controller.signal.aborted) setClerk(update);
    };
    annotate(
      { query: res.scope.topic || res.query, items },
      (event) => {
        if (event.type === "also_try") apply((prev) => ({ ...prev, alsoTry: event.suggestions }));
        else if (event.type === "themes") apply((prev) => ({ ...prev, themes: event.groups }));
      },
      controller.signal,
    )
      .catch(() => undefined) // the clerk is optional: the list stands without it
      .finally(() => apply((prev) => ({ ...prev, working: false })));
  }, []);

  const run = useCallback(
    async (text: string, nextScope: ScopeFilters, extracted: boolean, inside: Within | null, aside: string[]) => {
      const q = text.trim();
      if (!q) return;
      inflight.current?.abort();
      annotating.current?.abort();
      setClerk(NO_CLERK_WORK);
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
            exclude_item_ids: aside.length ? aside : undefined,
          },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setResult(res);
        setStatus("idle");
        startClerk(res);
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
    [setLog, startClerk],
  );

  const submit = useCallback(
    (text?: string) => {
      const q = text ?? query;
      if (text !== undefined) setQuery(text);
      setUseExtracted(true);
      setSetAside([]);
      void run(q, scope, true, within, []);
    },
    [query, scope, within, run],
  );

  const setScope = useCallback(
    (next: ScopeFilters) => {
      setScopeState(next);
      if (result) void run(query || result.query, next, useExtracted, within, setAside);
    },
    [result, query, useExtracted, within, setAside, run],
  );

  /**
   * Remove a chip that was read from the query. Extraction is switched off for
   * this query and the other extracted values become ordinary scope, so the
   * reader sees exactly what is applied.
   */
  const dropExtracted = useCallback(
    (key: keyof ScopeFilters, value?: string) => {
      const read = result?.scope;
      // Limits that were set aside (nothing matched them) stay aside; only exclusions applied.
      const extracted = read?.extracted_ignored ? { exclude: read.extracted.exclude } : read?.extracted ?? {};
      const next = mergeScope(scope, withoutScope(extracted, key, value));
      setScopeState(next);
      setUseExtracted(false);
      void run(query || result?.query || "", next, false, within, setAside);
    },
    [result, scope, query, within, setAside, run],
  );

  const restore = useCallback(
    (entry: LogEntry) => {
      setQuery(entry.query);
      setScopeState(entry.scope);
      setUseExtracted(true);
      setWithin(null);
      setSetAside([]);
      setRoom("desk");
      void run(entry.query, entry.scope, true, null, []);
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
        void run(query || result.query, scope, useExtracted, null, setAside);
      }
    },
    [result, query, scope, useExtracted, setAside, run],
  );

  const putAside = useCallback(
    (itemIds: string[] | null) => {
      const next = itemIds === null ? [] : Array.from(new Set([...setAside, ...itemIds]));
      setSetAside(next);
      if (result) void run(query || result.query, scope, useExtracted, within, next);
    },
    [setAside, result, query, scope, useExtracted, within, run],
  );

  const moreLike = useCallback(
    (item: DeskItem) => {
      const title = item.citation?.title || item.title;
      setQuery(title);
      setWithin(null);
      setSetAside([item.item_id]);
      setUseExtracted(false); // a title is a topic, never a scope phrase
      setRoom("desk");
      void run(title, scope, false, null, [item.item_id]);
    },
    [scope, run],
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
    room, setRoom, query, setQuery, scope, within, searchWithin, setAside, putAside, moreLike, pane, setPane, useExtracted, result, clerk, status, error,
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
