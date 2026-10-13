// Assert-based checks for the reference desk's pure helpers. Run: npm test (in frontend/).
import assert from "node:assert/strict";
import { reference, plain, shortCite, initials, sortName } from "../src/features/desk/cite.ts";
import { groupBy, refinements } from "../src/features/desk/facets.ts";
import { bibtex, pathfinder, ris } from "../src/features/desk/exports.ts";

const base = {
  item_id: "1", item_key: "K", group_id: null, pdf_key: null, short_title: "", date: "",
  container: "", volume: "", issue: "", pages: "", publisher: "", place: "", edition: "",
  report_number: "", thesis_type: "", doi: "", isbn: "", url: "",
};
const author = (first, last) => ({ first, last, role: "author" });
const item = (citation) => ({ citation, title: "", authors: "", year: null });

// Initials
assert.equal(initials("Jamie"), "J.");
assert.equal(initials("Mary-Jane Ann"), "M.-J. A.");
assert.equal(initials("J. R. R."), "J. R. R.");

// Book with two authors and an edition
const book = { ...base, item_type: "book", title: "The gig economy: A critical introduction", year: 2020,
  publisher: "Polity", edition: "2", creators: [author("Jamie", "Woodcock"), author("Mark", "Graham")] };
assert.equal(plain(reference(item(book))),
  "Woodcock, J., & Graham, M. (2020). The gig economy: A critical introduction (2nd ed.). Polity.");
assert.deepEqual(reference(item(book))[1], { text: "The gig economy: A critical introduction", italic: true });
assert.equal(shortCite(item(book)), "Woodcock & Graham (2020)");

// Journal article with volume, issue, pages and DOI
const article = { ...base, item_type: "journalArticle", title: "Riders on the storm", year: 2020,
  container: "Work, Employment and Society", volume: "34", issue: "1", pages: "35-54",
  doi: "https://doi.org/10.1177/0950017019862954",
  creators: [author("Arianna", "Tassinari"), author("Vincenzo", "Maccarrone"), author("A", "Third")] };
assert.equal(plain(reference(item(article))),
  "Tassinari, A., Maccarrone, V., & Third, A. (2020). Riders on the storm. Work, Employment and Society, 34(1), 35–54. https://doi.org/10.1177/0950017019862954");
assert.equal(shortCite(item(article)), "Tassinari et al. (2020)");

// Book section with editors; title ending in a question mark gets no extra stop
const section = { ...base, item_type: "bookSection", title: "Will unions survive?", year: 2021,
  container: "A modern guide", pages: "177-192", publisher: "Edward Elgar",
  creators: [author("Kurt", "Vandaele"), { first: "Jan", last: "Drahokoupil", role: "editor" }] };
assert.equal(plain(reference(item(section))),
  "Vandaele, K. (2021). Will unions survive? In J. Drahokoupil (Ed.), A modern guide (pp. 177–192). Edward Elgar.");

// Edited volume: editors stand in for authors
const edited = { ...base, item_type: "book", title: "Reader", year: null, publisher: "Duke",
  creators: [{ first: "Melissa", last: "Gregg", role: "editor" }, { first: "Gregory", last: "Seigworth", role: "editor" }] };
assert.equal(plain(reference(item(edited))), "Gregg, M., & Seigworth, G. (Eds.). (n.d.). Reader. Duke.");
assert.equal(shortCite(item(edited)), "Gregg & Seigworth (n.d.)");

// Long author lists: full in exports, shortened for display
const many = { ...base, item_type: "journalArticle", title: "Big", year: 2018, container: "J",
  creators: Array.from({ length: 22 }, (_, i) => author("A", `N${i}`)) };
assert.ok(plain(reference(item(many))).startsWith("N0, A., N1, A.,"));
assert.ok(plain(reference(item(many))).includes("N18, A., … N21, A. (2018)"));
assert.ok(plain(reference(item(many), 7)).startsWith("N0, A., N1, A., N2, A., N3, A., N4, A., N5, A., … N21, A. (2018)"));

// Without Zotero data, the index's own metadata still gives a usable line
const bare = { citation: null, title: "Cruel optimism", authors: "Berlant", year: 2011 };
assert.equal(plain(reference(bare)), "Berlant (2011). Cruel optimism.");
assert.equal(shortCite(bare), "Berlant (2011)");
assert.equal(sortName(bare), "berlant");

console.log("desk checks passed");

// Grouping by facet: rank order kept inside groups, unknown values last
const row = (id, citation, extra = {}) => ({ item_id: id, title: citation.title, authors: "", year: citation.year,
  item_type: citation.item_type, collections: [], citation, ...extra });
const rows = [row("a", article), row("b", book, { collections: ["Teaching"] }), row("c", { ...article, year: 2024 }),
  row("d", { ...book, year: null, creators: [] })];
assert.deepEqual(groupBy(rows, "decade", null).map((g) => [g.label, g.items.map((i) => i.item_id)]),
  [["2020s", ["a", "b", "c"]], ["Undated", ["d"]]]);
assert.deepEqual(groupBy(rows, "journal", null).map((g) => g.label), ["Work, Employment and Society", "Not in a journal or book"]);
assert.deepEqual(groupBy(rows, "author", null).map((g) => [g.label, g.items.length]), [["Tassinari", 2], ["Woodcock", 1], ["No author", 1]]);
assert.deepEqual(groupBy(rows, "collection", null).map((g) => g.label), ["Teaching", "In no collection"]);
assert.equal(groupBy(rows, "theme", null), null);
assert.deepEqual(groupBy(rows, "theme", [{ label: "Riders", item_ids: ["c", "a"] }]).map((g) => [g.label, g.items.map((i) => i.item_id)]),
  [["Riders", ["a", "c"]], ["Other", ["b", "d"]]]);
assert.equal(groupBy(rows, "none", null), null);

// BibTeX and RIS
assert.equal(bibtex([item(article)]), [
  "@article{tassinari2020riders,",
  "  author = {Tassinari, Arianna and Maccarrone, Vincenzo and Third, A},",
  "  title = {{Riders on the storm}},",
  "  journal = {Work, Employment and Society},",
  "  year = {2020},",
  "  volume = {34},",
  "  number = {1},",
  "  pages = {35--54},",
  "  doi = {10.1177/0950017019862954}",
  "}",
].join("\n"));
assert.match(bibtex([item(section), item(section)]), /@incollection\{vandaele2021will,[\s\S]*editor = \{Drahokoupil, Jan\}[\s\S]*booktitle = \{A modern guide\}[\s\S]*@incollection\{vandaele2021willb,/);
assert.match(bibtex([item({ ...book, title: "Profit & loss: 50% off" })]), /title = \{\{Profit \\& loss: 50\\% off\}\}/);
assert.equal(ris([item(section)]), [
  "TY  - CHAP", "AU  - Vandaele, Kurt", "ED  - Drahokoupil, Jan", "TI  - Will unions survive?", "T2  - A modern guide",
  "PY  - 2021", "SP  - 177", "EP  - 192", "PB  - Edward Elgar", "ER  - ",
].join("\r\n"));
assert.match(ris([{ citation: null, title: "Untitled draft", authors: "Woodcock", year: 2019 }]), /^TY  - GEN\r\nAU  - Woodcock\r\nTI  - Untitled draft\r\nPY  - 2019/);
// The index's authors field is comma-separated surnames; each becomes an author.
assert.match(bibtex([{ citation: null, title: "Three authors", authors: "Woodcock,Graham,de Beauvoir", year: 2019 }]),
  /author = \{Woodcock and Graham and de Beauvoir\}/);
assert.equal(plain(reference(item({ ...base, item_type: "journalArticle", title: "T", year: 2020, creators: [author("J", "W")], doi: "doi: 10.1/x" }))).endsWith("https://doi.org/10.1/x"), true);

// Refinements: busiest decade, most common collection, set the top rows aside
const listed = [2011, 2014, 2016, 2003, 2021, 2012].map((year, i) =>
  ({ ...row(String(i), { ...article, year }), rank: i + 1, collections: i < 2 ? ["ML"] : [] }));
assert.deepEqual(refinements(listed, {}).map((r) => [r.kind, r.label, r.count]),
  [["decade", "only the 2010s", 4], ["collection", "only in ML", 2], ["set_aside", "set the top 3 aside", 3]]);
assert.deepEqual(refinements(listed, {})[0], { kind: "decade", label: "only the 2010s", count: 4, year_min: 2010, year_max: 2019 });
assert.deepEqual(refinements(listed, {})[2].item_ids, ["0", "1", "2"]);
assert.deepEqual(refinements(listed.slice(0, 3), { year_min: 2010, collections: ["ML"] }), []);

// Pathfinder: groups, each entry with its extract when it has one; pinned passages last
const a = { ...row("a", article), extract: { text: "Couriers  used WhatsApp", page: 3, highlights: [] } };
const b = { ...row("b", book), extract: { text: "", page: null, highlights: [] } };
const md = pathfinder({ query: "courier strikes", scope: "since 2015", date: "11 October 2026",
  groups: [{ label: "Strikes", items: [a] }, { label: "Platforms", items: [b] }],
  pins: [{ label: "Tassinari et al. (2020)", page: 3, text: "Couriers used WhatsApp" }] });
assert.match(md, /^# Pathfinder: courier strikes\n\nSearched 11 October 2026 in my Zotero library, since 2015\./);
assert.match(md, /## Strikes\n\n1\. Tassinari, A\.[^\n]*\n   - “Couriers used WhatsApp” \(p\. 3\)/);
assert.match(md, /## Platforms\n\n2\. Woodcock[^\n]*\n\n## Pinned passages/);
assert.match(md, /## Pinned passages\n\n- Tassinari et al\. \(2020\), p\. 3: “Couriers used WhatsApp”/);
