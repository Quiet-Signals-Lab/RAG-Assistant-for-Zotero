// Formats two items in each bundled style through the real processor and checks the output.
// Run from the repository root:  node --experimental-strip-types frontend/scripts/csl.check.ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { formatReferences, toCsl } from "../src/features/desk/csl.ts";

const assets = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "assets", "csl");
const read = (name: string) => readFileSync(join(assets, name), "utf8");
const locale = read("locales-en-US.xml");

const article = {
  title: "", authors: "", year: 2020,
  citation: {
    item_id: "1", item_key: "A", item_type: "journalArticle", group_id: null, pdf_key: null,
    creators: [{ first: "Jamie", last: "Woodcock", role: "author" }, { first: "Mark", last: "Graham", role: "author" }],
    title: "The gig economy: A critical introduction", short_title: "", date: "2020-03-01", year: 2020,
    container: "Work, Employment and Society", volume: "34", issue: "2", pages: "341-352", publisher: "", place: "",
    edition: "", report_number: "", thesis_type: "", doi: "10.1177/0950017019890012", isbn: "", url: "",
  },
};
const fromIndex = { title: "A paper only the index knows", authors: "Tassinari,Maccarrone", year: 2019, citation: null };

const csl = toCsl(article, "x");
if (csl.type !== "article-journal" || (csl.issued as { "date-parts": number[][] })["date-parts"][0].join("-") !== "2020-3-1")
  throw new Error(`bad CSL-JSON: ${JSON.stringify(csl)}`);

const expect: Record<string, RegExp[]> = {
  "apa.csl": [/^Tassinari & Maccarrone\. \(2019\)\. A paper only the index knows\./, /Woodcock, J\., & Graham, M\. \(2020\)\. The gig economy.*Work, Employment and Society, 34\(2\), 341–352\. https:\/\/doi\.org\/10\.1177/],
  "chicago-author-date.csl": [/Woodcock, Jamie, and Mark Graham\. 2020\./],
  "chicago-notes-bibliography.csl": [/Woodcock, Jamie, and Mark Graham\. “The Gig Economy/],
};
for (const [style, patterns] of Object.entries(expect)) {
  const refs = formatReferences([article, fromIndex], read(style), locale);
  if (refs.length !== 2) throw new Error(`${style}: expected 2 references, got ${refs.length}`);
  for (const p of patterns) if (!refs.some((r) => p.test(r))) throw new Error(`${style}: no reference matches ${p}\n${refs.join("\n")}`);
  console.log(`${style}:\n  ${refs.join("\n  ")}`);
}
console.log("OK");
