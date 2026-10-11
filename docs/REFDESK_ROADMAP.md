# Reference Desk: implementation roadmap

Branch: `refdesk`. Companion to [REFERENCE_DESK_PLAN.md](REFERENCE_DESK_PLAN.md) (the why) and the "Reading Room, 1995" design canvas (the look: https://claude.ai/artifact/PbnLAq6girwGKddD5FkBMs).

**Decision change from the plan (2026-10-10):** chat is not removed in v0.7. It ships as a legacy mode, chosen in Settings → Interface. The reference desk is the default for new and existing installs. Chat code stays untouched apart from the shared restyle and the `retrieve()` refactor, so the toggle is cheap to keep and cheap to delete later.

Each stage ends with green tests (`pytest -m "not integration"`) and a clean frontend build (`npm run build:frontend`). Stages are committed separately.

---

## Stage 0 · Branch and roadmap
- [x] `refdesk` branch
- [x] This roadmap; plan updated for the legacy-toggle decision

## Stage 1 · Backend: the catalogue (retrieval and ranking; no model needed)

Pure, testable desk logic lives in a new `backend/desk.py`. The class keeps orchestration.

- [x] **1.1 Factor retrieval out of `ZoteroChatbot.chat()`** (as `_build_filter()` and `_search_and_rerank()`). Filters (extracted + manual + item ids), hybrid RRF search, auto-filter fallback, cross-encoder rerank. Returns docs, metadatas, rerank scores and the effective scope. `chat()` calls it with unchanged behaviour.
- [x] **1.2 Item-level results in `desk.py`.**
  - Dedupe overlapping passages within an item (same page, high token overlap) before anything is counted.
  - MaxP item score. Optional coverage bonus behind a constant set to 0.
  - Bands: strong / good / weak / see-also. Until per-reranker calibration exists (Stage 4) bands are assigned from the sigmoid of the cross-encoder logit with fixed cut-offs, kept in one place.
  - Query-biased extract: the sentence from the best passage with the most query terms, trimmed, with page.
- [x] **1.3 Deterministic known-item detection.** Quoted title, DOI, ISBN, arXiv id, author + year. Matched against item metadata (Zotero SQLite, read-only). Result pinned above the list, never replaces it.
- [x] **1.4 Bibliographic hydration.** `ZoteroLibrary.get_bibliographic(item_ids)`: item key, type, creators with roles, title, date, container, volume, issue, pages, publisher, DOI, URL. One batched read-only query per search; no reindex needed.
- [x] **1.5 `ZoteroChatbot.search()` and `POST /api/search`.** Desk retrieval limits independent of the chat model's context window (retrieve 60, rerank 40, up to 30 items, 3 passages each). Response shape as in the plan, plus `scope.extracted` so the UI can show what was read from the query.
- [x] **1.6 `interfaceMode` setting** (`"desk"` | `"chat"`, default `"desk"`) in backend default settings.
- [x] **1.7 Tests.** `test_desk.py` (dedupe, MaxP, bands, extract, known-item patterns, false-positive set), `test_zotero_bibliographic.py` (in-memory SQLite with the Zotero tables it touches), `test_search_api.py` (shape, no provider configured, filters passed through, 400 on empty query and empty scope).

## Stage 2 · Frontend: Reading Room theme and the desk

- [x] **2.1 Tokens.** `theme.css` moves to the Reading Room palette: paper, page, ink, rule, brass, stamp, catalogue blue; after-hours dark set. Radius 2 px, hairlines instead of shadows. `--font-mono` leads with IBM Plex Mono and falls back to the system mono (no font is fetched from the network; bundling Plex is an open decision). Legacy aliases kept so existing components keep resolving.
- [x] **2.2 Shared restyle.** `.btn` becomes flat, hairline, 2 px radius, sentence case; panels lose shadows and 16 px radii. Settings page inherits it through tokens. Legacy chat gets the new skin without behavioural change.
- [x] **2.3 Interface toggle.** `Settings.interfaceMode` in `SettingsContext`; Settings → General → Interface: "Reference desk (default)" / "Legacy chat". `AppShell` renders `DeskShell` or the existing chat shell.
- [x] **2.4 Desk state.** `features/desk/DeskContext.tsx`: query, scope chips, results, selection, pins, query log. `api/search.ts`.
- [x] **2.5 Query desk (left).** Query field, scope chips (year range, tags, collections, item types, author), dashed auto-extracted chips that can be removed, query log, rooms rail (desk, library, model, about).
- [x] **2.6 Bibliography (centre).** Known-item card pinned above the list, numbered rows, citation, mono meta line, extract with page, band marks, actions (open PDF, show in Zotero, pin), sort (relevance, year, author), "see also" fold, honest empty state.
- [x] **2.7 Evidence (right).** Passages for the selected item with stem-match highlighting, page, band, pin, open in Zotero at page; reading list of pins.
- [x] **2.8 Keyboard and responsive.** ↑/↓ rows, → evidence, `p` pin, `o` open, `/` query. Three panes ≥ 1100 px; evidence as an overlay 760–1099 px; one pane with Ask · Browse · Verify under 760 px.

- [x] **2.9 Settings and legacy chat in the Reading Room style.** Shared room header for all three rooms. Settings: section index, ledger rows (what the setting is | its controls), save bar; legacy-only settings say so. Legacy chat: full panes divided by hairlines, the desk's rail, mono turn labels ("Answer · written by the model"), sources and evidence as desk rows. Also fixed on the way: legacy evidence inserted PDF text as raw HTML; legacy sources showed an invented relevance percentage and loaded favicons from Google; the markdown repair split inline bold into paragraphs; Settings named the wrong licence (the project is GPL-3.0).

### Found by running Stages 1–2 on a real library (2026-10-11)

A throwaway index of 599 items built from Zotero abstracts, real reranker, real Zotero database:
- Scope phrases read from the query ("since 2010") are stripped before search and rerank; left in, they took the best score from 5.3 to −4.2.
- Unquoted title matching for known items needs 0.8 overlap; 0.6 pinned generic titles ("Adversarial machine learning") for topical queries.
- The same work stored twice in Zotero (same title, year and authors) is shown once, noting the duplicate.
- Passages that follow each other in an item drop the ~40 words the chunker repeats.
- The desk opens PDFs in Zotero's reader at the page through the attachment key; Electron now lets exactly `zotero://select` and `zotero://open-pdf` item links through.
- Warm searches take 0.4–1.0 s on an M-series Mac; the first search after start loads models and takes several seconds.

## Stage 3 · Desk depth
- [x] Query log and pins persisted per profile on the backend (`desk.json` next to `sessions.json`, `GET/PUT /api/profiles/{id}/desk`; browser-stored ones are moved over once)
- [x] Export: BibTeX and RIS (`features/desk/exports.ts`), besides copying APA references. Chicago is not done: a second hand-written style is the point at which citeproc-js and CSL earn their place
- [x] More like this: the item's title as the query, the item itself set aside (pearl growing). Not an item-level vector: the title search needs no index change and shows the reader what was searched
- [ ] Metadata-only browse (empty query + scope). Skipped: Zotero already browses by collection and tag, and a desk list without relevance would need rows with no band rather than a made-up one
- [x] Refinement chips: narrow to the busiest decade or the most common collection, set the top 3 aside
- [x] Group by facet: decade, kind of item, collection, first author, journal or book, and the clerk's themes
- [ ] Rocchio-style re-rank by pins (optional, model-free): not started

## Stage 4 · Index and measurement
- [ ] Contextual chunk headers (`{title} — {authors, year}`) and item key + DOI in chunk metadata, via a metadata-version migration. Waits for the test collection: it costs every user a full reindex, so it should ship with a measured gain
- [x] Test collection harness: `scripts/eval_ranking.py` pools queries (with intents), scores nDCG@10, P@5 and MRR, compares two runs with a sign test. The 40 judged queries themselves need the library's owner; judgments stay in the profile folder
- [x] Platt calibration fit (`eval_ranking.py calibrate`); replacing the fixed band cut-offs waits for real judgments
- [ ] Measure local fan-out latency (`llama-server -np 8`, 4B model) and record it. Measured instead through mlx_lm.server, one call at a time: see `docs/DESK_CLERK.md`

## Stage 5 · The desk clerk (tier 1, opt-in)
- [x] Structured output per provider (Ollama `format`, OpenAI/LM Studio `json_schema`, JSON mode elsewhere), one retry for malformed output, no retry after a guard failure: `backend/clerk.py`
- [x] Annotate stream: newline-delimited JSON, queued by what the reader sees first, cancelled by a new search; cached by job, model and input
- [x] Indicative notes behind the deterministic guard and an NLI entailment gate (passages, joined, three-sentence windows); extract fallback
- [x] Also-try selected from corpus vocabulary; BT / NT / RT from the words, not the model
- [x] Theme labels for k-means clusters; model query reading merged into the library reader's, each value tied to a phrase in the request
- [x] Measured-model register (`backend/clerk_models.json`, `scripts/eval_clerk.py --record`); "unmeasured" label for others
- [x] Clerk room on the rail: model, jobs, measurement; header status

## Stage 6 · The stacks
- [x] References and cited-by from the evidence pane via Semantic Scholar, owned items marked (by DOI, else exact title)
- [ ] Write-back to a Zotero collection (Zotero 10 local API, BBT fallback, feature-detected): not started; needs a Zotero to test against
- [x] Pathfinder export (Markdown: groups, notes or extracts, pinned passages). Tier 2 facets (place, method) not started
- [ ] Trigram keyword index; scripted berrypicking trail test: not started

## Stage 7 · Release
- [x] README rewrite: scoped claim, "what this app will never do", design rationale linked. Prior art stays in the plan
- [x] CHANGELOG with the migration note for chat users (where the toggle is)
- [ ] Screenshots: need a demo library, not a real one
- [ ] Published evaluation write-up
