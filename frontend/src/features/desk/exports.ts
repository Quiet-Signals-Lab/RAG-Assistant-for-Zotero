/**
 * Machine-readable exports of the list, so results go into any reference manager:
 * BibTeX and RIS from Zotero's structured fields. Items Zotero could not be read
 * for are exported from the index's own title, authors and year.
 */
import type { Citation, ClerkNote, Creator, DeskItem } from "../../types/desk";
// .ts extension: the node checks (scripts/desk.check.mjs) load this file without a bundler.
import { plain, primaryCreators, reference, type CitableItem } from "./cite.ts";

export type { CitableItem };

const BIBTEX_TYPE: Record<string, string> = {
  journalArticle: "article", magazineArticle: "article", newspaperArticle: "article",
  book: "book", bookSection: "incollection", conferencePaper: "inproceedings",
  thesis: "phdthesis", report: "techreport", preprint: "misc", webpage: "misc",
};

const RIS_TYPE: Record<string, string> = {
  journalArticle: "JOUR", magazineArticle: "MGZN", newspaperArticle: "NEWS", book: "BOOK",
  bookSection: "CHAP", conferencePaper: "CPAPER", thesis: "THES", report: "RPRT", webpage: "ELEC",
};

/** The citation, or one made from what the index knows. */
export function fields(item: CitableItem): Citation {
  if (item.citation) return item.citation;
  const creators = item.authors
    .split(/;|,(?=\s*[A-Z][^,]*$)/)
    .map((name) => name.trim())
    .filter(Boolean)
    .map((name): Creator => ({ first: "", last: name, role: "author" }));
  return {
    item_id: "", item_key: "", item_type: "document", group_id: null, pdf_key: null, creators, title: item.title,
    short_title: "", date: "", year: item.year, container: "", volume: "", issue: "", pages: "", publisher: "",
    place: "", edition: "", report_number: "", thesis_type: "", doi: "", isbn: "", url: "",
  };
}

function doiOf(doi: string): string {
  return doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").trim();
}

function name(c: Creator): string {
  return c.first ? `${c.last}, ${c.first}` : c.last;
}

function bibtexEscape(text: string): string {
  return text.replace(/([&%#_$])/g, "\\$1");
}

/** "woodcock2020gig": first author, year, first word of the title. */
function citeKey(c: Citation, seen: Map<string, number>): string {
  const ascii = (s: string) => s.normalize("NFD").replace(/[^\w]/g, "").toLowerCase();
  const last = ascii(primaryCreators(c).list[0]?.last ?? "") || "anon";
  const word = ascii(c.title.split(/\s+/).find((w) => w.length > 3) ?? "") || "item";
  const base = `${last}${c.year ?? ""}${word}`;
  const n = seen.get(base) ?? 0;
  seen.set(base, n + 1);
  return n ? `${base}${String.fromCharCode(97 + n)}` : base;
}

export function bibtex(items: CitableItem[]): string {
  const seen = new Map<string, number>();
  return items
    .map((item) => {
      const c = fields(item);
      const type = c.item_type === "thesis" && /master|msc|ma\b/i.test(c.thesis_type) ? "mastersthesis" : BIBTEX_TYPE[c.item_type] ?? "misc";
      const authors = c.creators.filter((x) => x.role !== "editor");
      const editors = c.creators.filter((x) => x.role === "editor");
      const container = type === "article" ? "journal" : type === "misc" ? "howpublished" : "booktitle";
      const publisherField = type === "techreport" ? "institution" : type.endsWith("thesis") ? "school" : "publisher";
      const entries: [string, string][] = [
        ["author", authors.map(name).join(" and ")],
        ["editor", editors.map(name).join(" and ")],
        ["title", c.title],
        [container, c.container],
        ["year", c.year ? String(c.year) : ""],
        ["volume", c.volume],
        ["number", c.issue || c.report_number],
        ["pages", c.pages.replace(/\s*[-–—]+\s*/g, "--")],
        [publisherField, c.publisher],
        ["address", c.place],
        ["edition", c.edition],
        ["type", type.endsWith("thesis") ? "" : c.thesis_type],
        ["doi", doiOf(c.doi)],
        ["isbn", c.isbn],
        ["url", c.url],
      ];
      const body = entries
        .filter(([, v]) => v)
        // Double braces keep the title's capitals; DOIs and URLs are not escaped.
        .map(([k, v]) => `  ${k} = {${k === "title" ? `{${bibtexEscape(v)}}` : k === "doi" || k === "url" ? v : bibtexEscape(v)}}`)
        .join(",\n");
      return `@${type}{${citeKey(c, seen)},\n${body}\n}`;
    })
    .join("\n\n");
}

export function ris(items: CitableItem[]): string {
  return items
    .map((item) => {
      const c = fields(item);
      const [start, end] = c.pages.split(/\s*[-–—]+\s*/);
      const lines: [string, string][] = [
        ["TY", RIS_TYPE[c.item_type] ?? "GEN"],
        ...c.creators.filter((x) => x.role !== "editor").map((x): [string, string] => ["AU", name(x)]),
        ...c.creators.filter((x) => x.role === "editor").map((x): [string, string] => ["ED", name(x)]),
        ["TI", c.title],
        ["T2", c.container],
        ["PY", c.year ? String(c.year) : ""],
        ["VL", c.volume],
        ["IS", c.issue || c.report_number],
        ["SP", start ?? ""],
        ["EP", end ?? ""],
        ["PB", c.publisher],
        ["CY", c.place],
        ["ET", c.edition],
        ["DO", doiOf(c.doi)],
        ["SN", c.isbn],
        ["UR", c.url],
      ];
      return [...lines.filter(([, v]) => v).map(([k, v]) => `${k}  - ${v}`), "ER  - "].join("\r\n");
    })
    .join("\r\n\r\n");
}

export interface PathfinderInput {
  query: string;
  scope: string;
  date: string;
  groups: { label: string; items: DeskItem[] }[];
  notes: Record<string, ClerkNote>;
  pins: { label: string; page: number | null; text: string }[];
}

/**
 * A pathfinder: the library's subject guide, as Markdown. The list in its groups,
 * each entry with the clerk's note (labelled) or its extract, then the pinned passages.
 */
export function pathfinder(p: PathfinderInput): string {
  const quote = (text: string) => text.replace(/\s+/g, " ").trim();
  const page = (n: number | null) => (n ? ` (p. ${n})` : "");
  const lines = [`# Pathfinder: ${p.query}`, "", `Searched ${p.date} in my Zotero library${p.scope ? `, ${p.scope}` : ""}.`, ""];
  let n = 0;
  for (const group of p.groups) {
    if (p.groups.length > 1) lines.push(`## ${group.label}`, "");
    for (const item of group.items) {
      n += 1;
      lines.push(`${n}. ${plain(reference(item))}`);
      const note = p.notes[item.item_id];
      if (note) lines.push(`   - Clerk's note (written by a model, checked against the passages): ${quote(note.note)}${page(note.page)}`);
      else if (item.extract.text) lines.push(`   - “${quote(item.extract.text)}”${page(item.extract.page)}`);
    }
    lines.push("");
  }
  if (p.pins.length) {
    lines.push("## Pinned passages", "");
    for (const pin of p.pins) lines.push(`- ${pin.label}${pin.page ? `, p. ${pin.page}` : ""}: “${quote(pin.text)}”`);
    lines.push("");
  }
  return lines.join("\n");
}
