/**
 * Repair the bold markup some models emit before it reaches the markdown renderer.
 *
 * Only bold that opens at the start of a line or after a space is treated as a
 * possible heading, so ordinary inline bold inside a sentence is left alone.
 * The earlier rules matched a closing `**` too, which split "**term** is…" into
 * two paragraphs and ran a following heading into the sentence before it.
 */
export function normaliseMarkdown(content: string): string {
  let s = content;
  // "**Title\n\n**" -> "**Title**": an opening ** separated from its closing one.
  s = s.replace(/(^|\s)\*\*([^\s*][^\n*]*?)\s*\n+\s*\*\*/gm, "$1**$2**");
  // "**\n\nTitle\n\n**" -> "**Title**": the markers on lines of their own.
  s = s.replace(/(^|\s)\*\*\s*\n+\s*([^\n*]+?)\s*\n+\s*\*\*/gm, "$1**$2**");
  // A bold heading run into the line before it: give it its own paragraph.
  s = s.replace(/([^\n])\n(\*\*[^*\n]+\*\*)/g, "$1\n\n$2");
  // A bold heading run into the text after it: "**Heading**Text" or "**Heading**\nText".
  s = s.replace(/^(\*\*[^*\n]+\*\*)(?=[\p{L}\p{N}])/gmu, "$1\n\n");
  s = s.replace(/^(\*\*[^*\n]+\*\*)\n(?=[^\n])/gm, "$1\n\n");
  return s;
}
