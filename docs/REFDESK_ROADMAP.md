# Reference Desk: implementation roadmap

Branch: `refdesk`. Companion to [REFERENCE_DESK_PLAN.md](REFERENCE_DESK_PLAN.md) (the why) and the "Reading Room, 1995" design canvas (the look: https://claude.ai/artifact/PbnLAq6girwGKddD5FkBMs).

**Decision change from the plan (2026-10-10):** chat is not removed in v0.7. It ships as a legacy mode, chosen in Settings → Interface. The reference desk is the default for new and existing installs. Chat code stays untouched apart from the shared restyle and the `retrieve()` refactor, so the toggle is cheap to keep and cheap to delete later.

Each stage ends with green tests (`pytest -m "not integration"`) and a clean frontend build (`npm run build:frontend`). Stages are committed separately.

---

## Stage 0 · Branch and roadmap
- [x] `refdesk` branch
- [x] This roadmap; plan updated for the legacy-toggle decision

## Stage 1 · Backend: the catalogue (no model on the critical path)

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

### Found by running Stages 1–2 on a real library (2026-10-11)

A throwaway index of 599 items built from Zotero abstracts, real reranker, real Zotero database:
- Scope phrases read from the query ("since 2010") are stripped before search and rerank; left in, they took the best score from 5.3 to −4.2.
- Unquoted title matching for known items needs 0.8 overlap; 0.6 pinned generic titles ("Adversarial machine learning") for topical queries.
- The same work stored twice in Zotero (same title, year and authors) is shown once, noting the duplicate.
- Passages that follow each other in an item drop the ~40 words the chunker repeats.
- The desk opens PDFs in Zotero's reader at the page through the attachment key; Electron now lets exactly `zotero://select` and `zotero://open-pdf` item links through.
- Warm searches take 0.4–1.0 s on an M-series Mac; the first search after start loads models and takes several seconds.

## Stage 3 · Desk depth
- [ ] Query log and pins persisted per profile on the backend (own file next to `sessions.json`, not the chat blob)
- [ ] Export: BibTeX, RIS, plain bibliography (APA, Chicago) for results or the reading list
- [ ] More like this (item-level vector) and metadata-only browse (empty query + scope)
- [ ] Refinement chips: narrow to decade, only this collection, exclude top 3
- [ ] Group by facet: period, form, collection, author, journal
- [ ] Rocchio-style re-rank by pins (optional, model-free)

## Stage 4 · Index and measurement
- [ ] Contextual chunk headers (`{title} — {authors, year}`) and item key + DOI in chunk metadata, via a metadata-version migration
- [ ] Test collection v1: 40 queries split by intent, pooled, paired comparisons; script under `scripts/`
- [ ] Per-reranker Platt calibration fitted on the test collection; replaces the fixed band cut-offs
- [ ] Measure local fan-out latency (`llama-server -np 8`, 4B model) and record it

## Stage 5 · The desk clerk (tier 1, opt-in)
- [ ] `provider_manager.complete_json()` with native schema modes and one retry
- [ ] Annotate stream (SSE) keyed by search id; cached by item + query hash; per-job budgets
- [ ] Indicative notes behind the deterministic guard and an NLI entailment gate; extract fallback
- [ ] Also-try selected from corpus vocabulary, typed BT / NT / RT
- [ ] Theme labels for k-means clusters; LLM scope extraction validated against library vocabulary
- [ ] Measured model allowlist; "unmeasured" label for others

## Stage 6 · The stacks
- [ ] References and cited-by from any row via the Semantic Scholar integration, owned items marked
- [ ] Write-back to a Zotero collection (Zotero 10 local API, BBT fallback, feature-detected)
- [ ] Pathfinder export; tier 2 facets (place, method)
- [ ] Trigram keyword index; scripted berrypicking trail test

## Stage 7 · Release
- [ ] README rewrite: scoped claim, prior art, "what this app will never do", design rationale with sources
- [ ] CHANGELOG, screenshots, migration note for chat users (where the toggle is)
- [ ] Published evaluation write-up
