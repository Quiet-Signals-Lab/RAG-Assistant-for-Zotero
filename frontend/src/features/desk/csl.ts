/**
 * References in any CSL style, through citeproc-js (the processor Zotero uses).
 * Zotero's fields become CSL-JSON; the style and locale XML are supplied by the
 * caller (bundled ones in styles.ts, or a style from Zotero's own styles folder).
 */
import CSL from "citeproc";
import type { Citation } from "../../types/desk";
import { doiOf, plain, reference } from "./cite.ts";
import { fields, type CitableItem } from "./exports.ts";

const CSL_TYPE: Record<string, string> = {
  journalArticle: "article-journal", magazineArticle: "article-magazine", newspaperArticle: "article-newspaper",
  book: "book", bookSection: "chapter", conferencePaper: "paper-conference", thesis: "thesis", report: "report",
  webpage: "webpage", preprint: "article", encyclopediaArticle: "entry-encyclopedia", dictionaryEntry: "entry-dictionary",
  manuscript: "manuscript", presentation: "speech", blogPost: "post-weblog", document: "document",
};
const CSL_ROLE: Record<string, string> = { author: "author", editor: "editor", translator: "translator" };

function issued(c: Citation): { "date-parts": number[][] } | undefined {
  const iso = /^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?/.exec(c.date || "");
  const parts = iso ? [iso[1], iso[2], iso[3]].filter(Boolean).map(Number) : c.year ? [c.year] : [];
  return parts.length ? { "date-parts": [parts] } : undefined;
}

/** One item as CSL-JSON. Creators with other roles (contributor, series editor) are left out. */
export function toCsl(item: CitableItem, id: string): Record<string, unknown> {
  const c = fields(item);
  const out: Record<string, unknown> = { id, type: CSL_TYPE[c.item_type] ?? "document", title: c.title || item.title };
  for (const creator of c.creators) {
    const role = CSL_ROLE[creator.role] ?? (creator.role === "contributor" ? "" : "author");
    if (!role) continue;
    (out[role] ??= []) as unknown[];
    (out[role] as unknown[]).push(creator.first ? { family: creator.last, given: creator.first } : { literal: creator.last });
  }
  const date = issued(c);
  if (date) out.issued = date;
  const text: [string, string][] = [
    ["container-title", c.container], ["volume", c.volume], ["issue", c.issue], ["page", c.pages], ["publisher", c.publisher],
    ["publisher-place", c.place], ["edition", c.edition], ["number", c.report_number], ["genre", c.thesis_type],
    ["DOI", doiOf(c.doi)], ["ISBN", c.isbn], ["URL", c.url], ["title-short", c.short_title],
  ];
  for (const [key, value] of text) if (value) out[key] = value;
  return out;
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

/** citeproc's HTML entries as plain text: tags dropped, entities decoded. */
function plainText(html: string): string {
  return html
    .replace(/<[^>]+>/g, "")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&([a-z]+);/g, (m, name) => ENTITIES[name] ?? m)
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The bibliography entries for `items`, in the order the style sorts them. An item a
 * style has no rendering for (citeproc reports it rather than printing a blank) falls
 * back to the desk's own APA reference, so every item is in the output.
 */
export function formatReferences(items: CitableItem[], styleXml: string, localeXml: string): string[] {
  const ids = items.map((_, i) => `item-${i}`);
  const byId = new Map(ids.map((id, i) => [id, toCsl(items[i], id)]));
  const engine = new CSL.Engine(
    { retrieveLocale: () => localeXml, retrieveItem: (id) => byId.get(id) ?? { id, type: "document" } },
    styleXml, "en-US", true,
  );
  engine.updateItems(ids);
  const made = engine.makeBibliography();
  if (!made) return items.map((item) => plain(reference(item)));
  const [meta, entries] = made;
  const failed = new Set(((meta.bibliography_errors as { itemID: string }[] | undefined) ?? []).map((e) => e.itemID));
  const order = ((meta.entry_ids as string[][] | undefined) ?? ids.map((id) => [id])).flat();
  let next = 0;
  return order.map((id) => (failed.has(id) ? plain(reference(items[ids.indexOf(id)])) : plainText(entries[next++] ?? "")))
    .filter(Boolean);
}
