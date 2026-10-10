// Assert-based checks for the reference desk's pure helpers. Run: npm test (in frontend/).
import assert from "node:assert/strict";
import { reference, plain, shortCite, initials, sortName } from "../src/features/desk/cite.ts";

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
