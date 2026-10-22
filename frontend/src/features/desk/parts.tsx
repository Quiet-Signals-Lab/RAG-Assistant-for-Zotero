/** Small presentational pieces shared by the desk's panels. */
import React from "react";
import type { Band, Citation, DeskItem, Span } from "../../types/desk";
import { buildZoteroOpenPdfUri, buildZoteroSelectUri, openLocalPdf, tryOpenZoteroUri } from "../../utils/zotero";
import { reference, type CitableItem } from "./cite";

/** Text with query terms marked. Spans are [start, end) offsets from the backend. */
export const Highlighted: React.FC<{ text: string; spans?: Span[] }> = ({ text, spans }) => {
  if (!spans?.length) return <>{text}</>;
  const parts: React.ReactNode[] = [];
  let at = 0;
  spans.forEach(([start, end], i) => {
    if (start < at || end > text.length) return;
    if (start > at) parts.push(text.slice(at, start));
    parts.push(<mark key={i}>{text.slice(start, end)}</mark>);
    at = end;
  });
  if (at < text.length) parts.push(text.slice(at));
  return <>{parts}</>;
};

export const Reference: React.FC<{ item: CitableItem; maxAuthors?: number }> = ({ item, maxAuthors = 7 }) => (
  <>
    {reference(item, maxAuthors).map((s, i) => (s.italic ? <i key={i}>{s.text}</i> : <React.Fragment key={i}>{s.text}</React.Fragment>))}
  </>
);

const BAND_LABEL: Record<Band, string> = { strong: "Strong", good: "Good", weak: "Weak", see_also: "See also" };
const BAND_FILLED: Record<Band, number> = { strong: 3, good: 2, weak: 1, see_also: 0 };

/** System relevance as ink weight, never a percentage. */
export const BandMark: React.FC<{ band: Band; small?: boolean; withLabel?: boolean }> = ({ band, small, withLabel }) => (
  <span className={`band${small ? " band--small" : ""}`} title={`${BAND_LABEL[band]} match`}>
    <span className="sr-only">{BAND_LABEL[band]} match</span>
    {band === "see_also" ? (
      <span className="band__dotted" aria-hidden="true" />
    ) : (
      <span className="band__segments" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} className={i < BAND_FILLED[band] ? "band__seg band__seg--on" : "band__seg"} />
        ))}
      </span>
    )}
    {withLabel && <span className="band__label" aria-hidden="true">{BAND_LABEL[band]}</span>}
  </span>
);

/** The first few words of a passage, enough to tell two from one page apart. */
export function opening(text: string): string {
  const words = text.replace(/^…/, "").split(/\s+/).filter(Boolean);
  return words.slice(0, 6).join(" ") + (words.length > 6 ? "…" : "");
}

/** "pp. 112–131", "p. 41", or "" when pages are unknown. */
export function pageSpan(pages: number[]): string {
  if (!pages.length) return "";
  const lo = pages[0];
  const hi = pages[pages.length - 1];
  return lo === hi ? `p. ${lo}` : `pp. ${lo}–${hi}`;
}

export function canOpenInZotero(c: Citation | null): boolean {
  return !!c?.pdf_key;
}

/** Open the PDF at a page: in Zotero's reader when the attachment is known, else the system viewer. */
export async function openPdf(item: Pick<DeskItem, "citation" | "pdf_path">, page?: number | null): Promise<void> {
  const c = item.citation;
  if (c?.pdf_key && tryOpenZoteroUri(buildZoteroOpenPdfUri(c.pdf_key, page ?? null, c.group_id))) return;
  if (item.pdf_path) return openLocalPdf(item.pdf_path);
  throw new Error("This item has no PDF to open.");
}

export function showInZotero(c: Citation | null): void {
  if (c) tryOpenZoteroUri(buildZoteroSelectUri(c.item_key, c.group_id));
}

export { itemTypeLabel } from "./cite";
