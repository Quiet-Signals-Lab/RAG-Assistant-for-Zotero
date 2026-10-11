/**
 * Grouping the list by a facet: Bates' area scanning and journal run, and the
 * plan's tier 0 facets (period, form, collection, author, journal) plus the
 * clerk's themes. Groups keep the list's order inside them.
 */
import type { DeskItem, ScopeFilters, Theme } from "../../types/desk";
// .ts extension: the node checks (scripts/desk.check.mjs) load this file without a bundler.
import { itemTypeLabel, primaryCreators } from "./cite.ts";

export type Facet = "none" | "theme" | "decade" | "type" | "collection" | "author" | "journal";

export const FACETS: { id: Facet; label: string }[] = [
  { id: "none", label: "none" },
  { id: "theme", label: "theme" },
  { id: "decade", label: "decade" },
  { id: "type", label: "kind of item" },
  { id: "collection", label: "collection" },
  { id: "author", label: "first author" },
  { id: "journal", label: "journal or book" },
];

export interface Group {
  label: string;
  items: DeskItem[];
}

/** Where an item lands when the facet has no value for it. */
const UNKNOWN: Partial<Record<Facet, string>> = {
  decade: "Undated",
  collection: "In no collection",
  author: "No author",
  journal: "Not in a journal or book",
};

function value(item: DeskItem, facet: Facet): string {
  const c = item.citation;
  switch (facet) {
    case "decade": {
      const year = c?.year ?? item.year;
      return year ? `${Math.floor(year / 10) * 10}s` : "";
    }
    case "type":
      return itemTypeLabel(c?.item_type || item.item_type);
    case "collection":
      return item.collections[0] ?? "";
    case "author":
      return (c ? primaryCreators(c).list[0]?.last : item.authors.split(",")[0])?.trim() ?? "";
    case "journal":
      return c?.container.trim() ?? "";
    default:
      return "";
  }
}

/** The list as groups, or null for no grouping (or themes not yet named). */
export function groupBy(items: DeskItem[], facet: Facet, themes: Theme[] | null): Group[] | null {
  if (facet === "none") return null;
  if (facet === "theme") {
    if (!themes) return null;
    const placed = new Set(themes.flatMap((t) => t.item_ids));
    return [
      ...themes.map((t) => ({ label: t.label, items: items.filter((it) => t.item_ids.includes(it.item_id)) })),
      { label: "Other", items: items.filter((it) => !placed.has(it.item_id)) },
    ].filter((g) => g.items.length);
  }
  const byValue = new Map<string, DeskItem[]>();
  for (const item of items) {
    const key = value(item, facet);
    byValue.set(key, [...(byValue.get(key) ?? []), item]);
  }
  const groups = [...byValue].filter(([key]) => key).map(([label, list]) => ({ label, items: list }));
  if (facet === "decade") groups.sort((a, b) => b.label.localeCompare(a.label));
  else groups.sort((a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label));
  const rest = byValue.get("");
  if (rest) groups.push({ label: UNKNOWN[facet] ?? "Other", items: rest });
  return groups;
}

export type Refinement =
  | { kind: "decade"; label: string; count: number; year_min: number; year_max: number }
  | { kind: "collection"; label: string; count: number; collection: string }
  | { kind: "set_aside"; label: string; count: number; item_ids: string[] };

/**
 * Ways to narrow the list that the list itself suggests: its busiest decade, its
 * most common collection, or setting the top rows aside to see what else there is.
 * Offered only when they would change the list.
 */
export function refinements(listed: DeskItem[], scope: ScopeFilters): Refinement[] {
  const out: Refinement[] = [];
  if (!scope.year_min && !scope.year_max) {
    const decades = groupBy(listed, "decade", null)?.filter((g) => g.label !== "Undated") ?? [];
    const top = [...decades].sort((a, b) => b.items.length - a.items.length)[0];
    if (decades.length > 1 && top.items.length > 1) {
      const start = parseInt(top.label, 10);
      out.push({ kind: "decade", label: `only the ${top.label}`, count: top.items.length, year_min: start, year_max: start + 9 });
    }
  }
  const counts = new Map<string, number>();
  for (const item of listed) for (const c of new Set(item.collections)) counts.set(c, (counts.get(c) ?? 0) + 1);
  const [collection, n] = [...counts].filter(([c]) => !scope.collections?.includes(c)).sort((a, b) => b[1] - a[1])[0] ?? [];
  if (collection && n && n > 1 && n < listed.length) {
    out.push({ kind: "collection", label: `only in ${collection}`, count: n, collection });
  }
  if (listed.length > 5) {
    const top = [...listed].sort((a, b) => a.rank - b.rank).slice(0, 3);
    out.push({ kind: "set_aside", label: "set the top 3 aside", count: 3, item_ids: top.map((it) => it.item_id) });
  }
  return out;
}
