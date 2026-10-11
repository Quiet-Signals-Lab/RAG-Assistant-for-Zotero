/**
 * Citation formatting for the reference desk: APA 7 style references from
 * Zotero's structured fields, and short author-year labels.
 *
 * shortcut: a hand-written APA subset for the common item types; switch to
 * citeproc-js with CSL styles when export needs more than APA (roadmap Stage 3).
 */
import type { Citation, Creator } from "../../types/desk";

export type Segment = { text: string; italic?: boolean };

/** What a row knows even when Zotero could not be read: the index's own metadata. */
export interface CitableItem {
  citation: Citation | null;
  title: string;
  authors: string;
  year: number | null;
}

const PRIMARY_ROLES = new Set([
  "author", "artist", "cartographer", "director", "interviewee", "inventor",
  "performer", "podcaster", "presenter", "programmer", "sponsor",
]);

function initial(part: string): string {
  return /^(\p{Lu}\.)+$/u.test(part) ? part : part.charAt(0).toUpperCase() + ".";
}

export function initials(first: string): string {
  return first
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.split("-").filter(Boolean).map(initial).join("-"))
    .join(" ");
}

function apaName(c: Creator): string {
  return c.first ? `${c.last}, ${initials(c.first)}` : c.last;
}

/** APA lists up to 20 authors; beyond `max`, the first max-1, an ellipsis, then the last. */
function apaNames(creators: Creator[], max = 20): string {
  const names = creators.map(apaName);
  if (names.length <= 1) return names[0] ?? "";
  if (names.length <= max) return `${names.slice(0, -1).join(", ")}, & ${names[names.length - 1]}`;
  return `${names.slice(0, max - 1).join(", ")}, … ${names[names.length - 1]}`;
}

/** Authors, or editors when an item has no author (an edited volume). */
export function primaryCreators(c: Citation): { list: Creator[]; editors: boolean } {
  const primary = c.creators.filter((x) => PRIMARY_ROLES.has(x.role));
  if (primary.length) return { list: primary, editors: false };
  return { list: c.creators.filter((x) => x.role === "editor"), editors: true };
}

function enDash(pages: string): string {
  return pages.replace(/\s*-+\s*/g, "–");
}

function edition(value: string): string {
  const n = parseInt(value, 10);
  if (!n || String(n) !== value.trim()) return value;
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th";
  return `${n}${suffix}`;
}

function stop(text: string): string {
  return /[.?!]$/.test(text.trim()) ? "" : ".";
}

/** Merge plain neighbours and normalise spacing so the reference reads as one sentence. */
function tidy(segments: Segment[]): Segment[] {
  const out: Segment[] = [];
  for (const s of segments) {
    if (!s.text) continue;
    const last = out[out.length - 1];
    if (last && !last.italic && !s.italic) last.text += s.text;
    else out.push({ ...s });
  }
  for (const s of out) s.text = s.text.replace(/\s{2,}/g, " ").replace(/\.\./g, ".");
  if (out.length) out[out.length - 1].text = out[out.length - 1].text.trimEnd();
  return out;
}

/** `maxAuthors` shortens long author lists for display; exports keep APA's 20. */
export function reference(item: CitableItem, maxAuthors = 20): Segment[] {
  const c = item.citation;
  if (!c) {
    const who = item.authors ? item.authors.split(",").map((s) => s.trim()).filter(Boolean).join(", ") + " " : "";
    return tidy([{ text: `${who}(${item.year ?? "n.d."}). ` }, { text: item.title || "Untitled", italic: true }, { text: "." }]);
  }

  const seg: Segment[] = [];
  const { list, editors } = primaryCreators(c);
  const who = apaNames(list, maxAuthors);
  const role = editors && list.length ? (list.length > 1 ? " (Eds.)." : " (Ed.).") : "";
  seg.push({ text: who ? `${who}${role} (${c.year ?? "n.d."}). ` : `(${c.year ?? "n.d."}). ` });

  const title = c.title || item.title || "Untitled";
  const pages = c.pages ? enDash(c.pages) : "";

  switch (c.item_type) {
    case "book": {
      const ed = c.edition ? ` (${edition(c.edition)} ed.)` : "";
      seg.push({ text: title, italic: true }, { text: `${ed}${stop(title + ed)} ` });
      if (c.publisher) seg.push({ text: `${c.publisher}.` });
      break;
    }
    case "bookSection":
    case "encyclopediaArticle":
    case "dictionaryEntry": {
      seg.push({ text: `${title}${stop(title)} ` });
      if (c.container) {
        const eds = c.creators.filter((x) => x.role === "editor");
        const edNames = eds.map((e) => `${e.first ? initials(e.first) + " " : ""}${e.last}`);
        const edText = edNames.length ? `${edNames.join(edNames.length > 2 ? ", " : " & ")} (${eds.length > 1 ? "Eds." : "Ed."}), ` : "";
        seg.push({ text: `In ${edText}` }, { text: c.container, italic: true }, { text: `${pages ? ` (pp. ${pages})` : ""}. ` });
      }
      if (c.publisher) seg.push({ text: `${c.publisher}.` });
      break;
    }
    case "journalArticle":
    case "magazineArticle":
    case "newspaperArticle": {
      seg.push({ text: `${title}${stop(title)} ` });
      if (c.container) {
        seg.push({ text: c.container, italic: true });
        if (c.volume) seg.push({ text: ", " }, { text: c.volume, italic: true });
        if (c.issue) seg.push({ text: `(${c.issue})` });
        if (pages) seg.push({ text: `, ${pages}` });
        seg.push({ text: ". " });
      }
      break;
    }
    case "conferencePaper": {
      seg.push({ text: `${title}${stop(title)} ` });
      if (c.container) seg.push({ text: "In " }, { text: c.container, italic: true }, { text: `${pages ? ` (pp. ${pages})` : ""}. ` });
      if (c.publisher) seg.push({ text: `${c.publisher}.` });
      break;
    }
    case "report": {
      const number = c.report_number ? ` (Report No. ${c.report_number})` : "";
      seg.push({ text: title, italic: true }, { text: `${number}${stop(title + number)} ` });
      if (c.publisher) seg.push({ text: `${c.publisher}.` });
      break;
    }
    case "thesis": {
      seg.push({ text: title, italic: true }, { text: ` [${c.thesis_type || "Thesis"}${c.publisher ? `, ${c.publisher}` : ""}].` });
      break;
    }
    default: {
      seg.push({ text: title, italic: true }, { text: `${stop(title)} ` });
      if (c.container) seg.push({ text: c.container, italic: true }, { text: ". " });
      else if (c.publisher) seg.push({ text: `${c.publisher}.` });
    }
  }

  if (c.doi) seg.push({ text: ` https://doi.org/${c.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")}` });
  return tidy(seg);
}

export function plain(segments: Segment[]): string {
  return segments.map((s) => s.text).join("");
}

/** "Woodcock & Graham (2020)", "Tassinari et al. (2020)", "Polity (n.d.)". */
export function shortCite(item: CitableItem): string {
  let names: string[];
  let year = item.year;
  if (item.citation) {
    names = primaryCreators(item.citation).list.map((c) => c.last).filter(Boolean);
    year = item.citation.year ?? year;
  } else {
    names = item.authors.split(",").map((s) => s.trim()).filter(Boolean);
  }
  const who =
    names.length === 0 ? (item.citation?.title || item.title || "Untitled") :
    names.length === 1 ? names[0] :
    names.length === 2 ? `${names[0]} & ${names[1]}` :
    `${names[0]} et al.`;
  return `${who} (${year ?? "n.d."})`;
}

/** The first author's last name, for sorting. */
export function sortName(item: CitableItem): string {
  const first = item.citation ? primaryCreators(item.citation).list[0]?.last : item.authors.split(",")[0];
  return (first || item.citation?.title || item.title || "").trim().toLocaleLowerCase();
}

/** "journal article" from Zotero's "journalArticle". */
export function itemTypeLabel(type: string): string {
  return type.replace(/([a-z])([A-Z])/g, "$1 $2").toLocaleLowerCase();
}
