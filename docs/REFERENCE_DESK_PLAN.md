# Reference Desk Plan (3rd edition, 2026-10-10)

Zotero RAG Assistant, v0.7 through v1.0. A reference desk for your Zotero library: you ask, the catalogue hands back a bibliography with the evidence open at the page, and you decide what is true.

This edition was revised against a deep-research audit of the second (prior art, retrieval literature, small-model evidence, Zotero community norms) and against the codebase. The styled version lives at https://claude.ai/artifact/V9FbvkPL3YRmRnMJnkESuD; the audit at https://claude.ai/artifact/Tnri95iCTtXqbFv2EqX4pJ.

## 1. Decisions already made

These are settled. The rest of the plan assumes them.

- **Free, with no monetisation.** No tiers, no keys sold, no telemetry. The product exists to be excellent and to carry the Quiet Signals Lab name.
- **No answers, ever.** No code path asks a model to answer a question or synthesise across documents. "Do these five papers agree?" is out of scope by design, and the README says so.
- **Chat becomes a legacy mode.** The desk is the default from v0.7. Chat stays available behind Settings → Interface for existing users and is not developed further. (Revised 2026-10-10; the original plan removed it outright.)
- **Model use is a choice, not a rule.** The desk can run with no model, and a model can work before the list appears (reading the query) or after it (notes, labels). Which of these is on is a setting. (Corrected 2026-10-11: earlier editions listed "works fully with no model" and "zero model calls before first paint" as decisions. They were proposals and were never agreed.)
- **Local-first by default.** Nothing leaves the machine unless the user configures a cloud provider or supplies their own key for an external service.
- **A place, not a persona.** "A reference desk for your Zotero library", never "your AI librarian".
- **Small codebase.** Single-maintainer plugins in this ecosystem die at Zotero major-version boundaries. Deletion is a feature.

## 2. Why leave the chat window

A chat box asks a question and expects an answer. That nudges people toward truth-seeking rather than source discovery, and puts a model on the critical path of every query, which is where small local models fail. Showing citations *increases* trust in model answers even when the citations are random; trust only falls when people actually check them (Ding et al., AAAI 2025). An interface where checking is the primary act is the only honest design for a research tool.

The backend already is a search engine. Everything in `ZoteroChatbot.chat()` (`backend/interface.py`) up to the cross-encoder rerank produces a ranked bibliography with evidence attached. The chatbot is the last two steps. This plan stops at step three and renders it.

**The profession already learned this lesson.** Hernon and McClure's 55 percent rule (1986) measured short factual questions and was contested, but the response matters: Durrance (1989) showed users judge a reference encounter by process transparency and follow-up, not answer accuracy; behavioural training raised performance (Gers and Seward 1985); the RUSA behavioural guidelines (2023 revision) encode it: clarify, search with the user, show what was found and where, follow up. Never give an opinion. ACRL's framework: searching is strategic exploration; authority is constructed and contextual.

**Ranganathan's Five Laws, five commitments:**

| Law | Commitment |
|---|---|
| Books are for use | Every row is one click from the PDF at the page and one click from the item in Zotero |
| Every reader their book | The reference interview comes first; the desk shows how it read the query and makes correction cheaper than retyping |
| Every book its reader | "See also" fold, pearl growing, browse by scope surface what you forgot you own |
| Save the time of the reader | Bibliography in about 2 s; any model step that delays it is one the reader turned on, with a time limit |
| The library is a growing organism | Query log, pins and reading lists accumulate; nothing is discarded, because there is no conversation |

One rule above the five, our own principle derived from professional norms: **the desk answers with sources, never with claims.**

## 3. Prior art and the claim we can make

The strong claim (nobody has built retrieval-first local search over Zotero) is false: ZotSeek shipped it in December 2025. The narrow claim survives: no one has combined retrieval-first results, a decoration-only local model, and the profession's written methods, over a personal library.

| Nearest neighbours | What they are | What they lack |
|---|---|---|
| ZotSeek (2025) | Local hybrid search over Zotero, passage and page hits, no cloud by design | No model layer, facets, trails or export |
| Beaver, PapersGPT, Zotero GPT, Aria | Chat over the library, real retrieval underneath in the better ones | Answer-first. Beaver is one decision from this territory |
| zotero-mcp and kin | Expose the library to an external chat client | Infrastructure, not an interface |
| Ai2 Paper Finder (2025) | Ranked open-literature list with per-paper relevance notes | Cloud, open corpus; known-item mode "often failed" |
| PaperWeaver, Scim, CiteSee (CHI 2023–24) | Per-paper blurbs relative to a collection | Prototypes; closest precedent to the indicative note |
| DEVONthink (2009–) | Statistical see-also over a personal corpus | Proof users accept rank-and-suggest; no scholarly structure |
| Khoj (2022–24) | Began as search over personal notes | Pivoted to answer-first chat. The cautionary tale |
| Legal citators (Shepard's, KeyCite, Filevine LOIS 2026) | Decoration over citation-graph retrieval | Legal, cloud, paid; evidence that decoration survives where answers fail audits |

Older still: query-biased snippets (Tombros and Sanderson 1998), cluster labelling (Vivísimo, Carrot2), relevance feedback (Rocchio 1971). The README names all of these.

## 4. The models we borrow

| Model | What it says | Where it lives |
|---|---|---|
| Cutter's objects of the catalogue (1876) | Find a known item; show what the library has on a subject; assist choice among editions | Known-item pin above the list; browse by scope; full citation on the row |
| IFLA LRM (2017; consolidates FRBR, FRAD, FRSAD) | Find, identify, select, obtain, and LRM's addition, explore | The panel contract: list = find/identify; evidence = select; actions = obtain; facets and pearl growing = explore |
| Taylor (1968): levels of need, five filters | The typed query is the compromised need, three levels from the visceral one | Extracted scope as removable dashed chips; rewrite shown, not hidden |
| Dervin and Dewdney (1986), neutral questioning | Leading questions distort the interview | Refinement chips are offered, never pre-applied; the log makes every step reversible |
| Belkin (1982), ASK | People often cannot specify the need; browsing precedes querying | Empty query with filters is a valid search |
| Bates (1989), berrypicking and six strategies | Searches are evolving trails; six strategies alternate | Query log as first-class object; pins persist; six strategies, six controls |
| Kuhlthau (1991; zone of intervention from *Seeking Meaning*, 1993) | Uncertainty peaks in exploration | The desk is built for exploration and collection; the model only extracts, labels and suggests |
| Marchionini (2006); White and Roth (2009) | Exploratory search is its own system category | Names what the desk is; their criteria are the UI review checklist |
| Hearst (2009); Flamenco (Yee et al. 2003) | Users prefer trustworthy metadata facets; generated facets rank below | Metadata facets ship first; model facets are a later gated tier |
| Saracevic (1975; 2007 Parts II–III) | At least five manifestations of relevance | The band is system relevance, drawn as a band, never a number; the pin is situational relevance; never merged |
| Rocchio (1971) | Marked-relevant documents reshape the query | Optional model-free re-rank from pins |
| Ranganathan (1933), facets | Subjects are compound | Group-by is faceted; facets combine |
| ISO 25964, thesaurus relationships | BT, NT, RT, use-for | Also-try chips typed BT/NT/RT; candidates from the corpus, model only selects |
| Tombros and Sanderson (1998) | Query-biased extracts beat static abstracts | The default note under every row is an extract |
| ANSI/NISO Z39.14 | Indicative vs informative abstracts; the standard prefers informative | Deliberately inverted: the note is a pointer and the reader is one click from the page; model notes are indicative and descriptive only |
| Garfield (1955) | The literature is a network | References and cited-by on any row via the existing Semantic Scholar integration |
| Pirolli and Card (1999) | Scent and patch-leaving | Highlights and extracts are scent; "see also" is the patch boundary |
| Lown et al.; Asher et al. (2013) | Known-item intent is large; default ranking decides what gets read | Known-item route; ranking is the most consequential line of code |
| Cranfield (1967) and its limits | Static topical relevance cannot evaluate berrypicking | Pooled test collection plus scripted multi-query trails |

## 5. The workflow

Three panels, three verbs: **ask** (left), **browse** (centre), **verify** (right). Everything renders with no model configured. Where a model is enabled it adds a labelled note line and typed also-try chips, after the list is on screen.

### 5.1 Three tiers, one product

| Tier | Requirement | Adds | Default |
|---|---|---|---|
| 0 · The catalogue | None. The local cross-encoder reranker is the only model and is always on | Hybrid retrieval, item-level ranking, extractive query-biased notes, metadata facets (period, form, collection, author, journal), regex scope extraction, regex known-item pin, pearl growing, citation chaining with the user's key, query log, pins, exports | Every install |
| 1 · The desk clerk | A grounded model from a measured allowlist: 4B-class local (Qwen3-4B, Gemma 4 E4B class, measured in-house) or any cloud provider | Abstractive indicative notes behind a deterministic check and an entailment gate (extract as fallback); LLM scope extraction; corpus-selected also-try; theme labels | Opt-in. Local: notes on, themes off. Cloud: both on |
| 2 · The subject specialist | 9B-class local or cloud | Place and method facets; pathfinder annotations | Opt-in |

**Never, at any tier:** answering the question; synthesis across items; known-item routing by model; free generation of search terms.

Latency budgets are unmeasured. Audit extrapolation: 8–15 s for 25 notes on an M4 Pro with eight slots and a cached shared prefix; far worse on a base M1 16 GB. Phase 0 measures with `llama-server -np 8` before any number appears in a README.

### 5.2 Left panel: the query desk

- **Two kinds of question.** Known-item queries ("the Woodcock book", "Tassinari 2020", a DOI) get deterministic high-precision detection: quoted string, author-year pattern, title n-gram containment ≥ ~0.6, DOI/arXiv/ISBN. A hit is **pinned as a card above** the ranked list, never substituted for it.
- **Query box.** One field, Enter to search, the query stays visible. Quoted phrases work. Field prefixes (`author:`, `year:`, `tag:`) supported but not advertised.
- **Scope chips.** Year, tags, collections, item types, author, journal. Already present as `manualFilters` in `SearchSettingsContext` and `manual_filters` on the backend; they move to the surface.
- **Auto-extracted scope** shown as dashed, removable chips. Regex is the floor; the LLM path at tier 1 writes to the same chips.
- **Refinement chips.** "Narrow to this decade", "only this collection", "exclude the top 3", "more like item 1". Each edits the query object and re-runs in place. Offered, never auto-applied.
- **Query log.** Replaces threads. One row per query with filters, result count and pins. Stored per profile through the existing sessions endpoint.
- **Also try** (tier 1). Candidates from the result set's tags, title n-grams and co-occurring vocabulary; the model selects and types them BT/NT/RT. Labelled "from your tags".
- **Browse.** Filters with no query return the scope ordered by year.

Bates' six strategies, six controls, all tier 0: subject search (query box); author search (author chip, "other works by"); footnote chasing ("References" via Semantic Scholar, owned items marked); citation searching ("Cited by"); journal run (group by journal); area scanning ("more like this", browse by scope).

### 5.3 Centre panel: the bibliography

Row anatomy: rank; citation (hydrated from Zotero via the existing item-metadata endpoint, batched; item key and DOI join chunk metadata at next reindex); **extract** (default note: the clause from the best passage with the most query terms, with page); **note** (tier 1, labelled, replaces the extract only when it passes both guards); **band** (strong / good / weak / see also, never a number anywhere); badges; actions (select in Zotero, open PDF at page, pin, more like this, references, cited by, exclude).

Ranking:

```
passages   = dedupe_overlaps(chunks_for_item)       # 200-char overlap can count a passage twice
item_score = max(p.rerank_score for p in passages)   # MaxP: Dai & Callan 2019
# optional, flag off, BONUS = 0 until the test collection shows a paired win:
item_score += BONUS * log(1 + count(p for p in passages if p.band >= good))
```

Reranker scores are uncalibrated logits. Calibration is per reranker model, fitted once on the test collection with Platt scaling, stored next to the model config, exposed only as bands.

Controls: sort (relevance, year, first author, date added); group by facet (tier 0: period, form, collection, author, journal; tier 1: theme; tier 2: place, method); "see also" fold; multi-select.

Export: CSL via citeproc-js (AGPL, at arm's length in the renderer; start with APA and Chicago, accept any CSL file); BibTeX and RIS; pathfinder (themed, annotated bibliography with extracts/notes and pinned passages); write back to a Zotero collection via Zotero 10 local write API with Better BibTeX JSON-RPC fallback on Zotero 7–9, feature-detected, never writing to SQLite directly.

### 5.4 Right panel: the evidence

The LRM select task. Passages for the selected item ordered by band, with page and surrounding paragraph on expand; stem-match highlighting, no model; open PDF at page (`zotero://open-pdf/library/items/KEY?page=N`); pin (persists with the query, forms the reading list, feeds the pathfinder, optional Rocchio re-rank); merged view for multi-select; "matched by scope only" state.

## 6. The librarian's jobs

Every model call: short input, short output, strict schema, stratified by risk. Query reading may run before the search; the other jobs run after the list appears. Grounded jobs over supplied passages are the safe ones; anything leaning on parametric knowledge (free term suggestion) is the dangerous one.

| Job | Tier | Input | Output | Guard | Without a model |
|---|---|---|---|---|---|
| Known-item detection | 0 | query | regex only, no model at any tier | pin above list | this is the design |
| Scope extraction | 1 | query ≤ 200 chars | `{year_min, year_max, tags[], collections[], author, item_types[]}` | values must exist in library vocab; shown as chips | regex extractor (exists) |
| Indicative note | 1 | query + top 3 passages ≤ 2,400 chars | `{note}`, one sentence, descriptive, cites a page | deterministic (page exists, no foreign author/title) then NLI entailment (HHEM-2.1-Open or MiniCheck class, CPU); below threshold → extract | extract (the default) |
| Also try | 1 | query + candidate terms from tags, title n-grams, co-occurrence | `{broader, narrower[1..2], related}` as candidate ids | selection only; non-candidates dropped | omit |
| Theme labels | 1 | titles per k-means cluster | `{labels:[{cluster,label}]}` ≤ 4 words | label shares a content word with a title in its cluster | metadata facets only |
| Place / method facets | 2 | titles + passages | `{place[], method[]}` | value appears verbatim in input | omit |
| Pathfinder annotation | 2, on demand | pinned passages | `{annotation}`, two sentences | same two checks as the note | pins verbatim |

The guard-rail, honestly: the deterministic check removes the cheapest hallucination paths; the entailment gate catches some of the rest; the best published detectors reach about 50 percent on hard cases. Both together are mitigation, not certification. Hence extract by default, note as upgrade, note always labelled.

Plumbing: one `complete_json()` helper on the provider manager (schema in prompt, native JSON-schema mode where available, parse, validate, retry once, fall back); one annotate stream over SSE keyed by search id, cached by item and query hash; per-job budgets and cancellation (never a modal); shared-prefix KV caching and parallel slots for local runtimes; a measured model allowlist with an "unmeasured" label for anything else.

## 7. Retrieval changes, in priority order

1. **Contextual chunk headers at the next reindex.** Prepend `{title} — {authors, year} — {section if known}` to every chunk in both indexes. Chunks embed as raw text today (`_index_one`). Best-evidenced improvement available; rides on the reindex needed for item keys and DOIs via the metadata version system.
2. **Lift the context cap.** `get_retrieval_limits()` sizes results to the model's context window. Retrieve 60, rerank to 40, show up to 30 items with 3 passages each.
3. **Item-level ranking** as above.
4. **Calibrated bands** per reranker.
5. **Known-item route** via the existing item-search endpoint, pinned above the list.
6. **More like this at the item level.** Title-plus-abstract item vectors beat chunk centroids; SPECTER2 optional at the item layer. Pair with the vocabulary move (re-run with the item's tags and title terms).
7. **Metadata-only browse** via a Chroma where-clause with no query.
8. **Keyword index precision.** The index already splits CJK into character tokens before FTS5 (`vector_db.py`), so it works today. A trigram tokenizer improves CJK precision and partial-title matching at 3–5× index size. Worth doing, not urgent.
9. **Embedder upgrades.** bge-m3 stays the default for multilingual libraries; evaluate Qwen3-Embedding-0.6B and EmbeddingGemma once the test collection exists. Ignore deltas under ~2 points.
10. **Deferred.** Late chunking, ColBERT-style multi-vector, SPLADE.

## 8. Codebase changes

Factor, then delete. The retrieval half of `chat()` becomes a function; the desk calls it; chat is removed in the same release.

### Backend

| Piece | Fate | Detail |
|---|---|---|
| `interface.py` chat() steps 2–3 | factor | `retrieve(query, filters, k) → {items[], passages[]}`: extraction, hybrid search, fallback, rerank, overlap dedupe, item scoring, bands, extracts |
| `POST /api/search` | new | Calls `retrieve()`. No session, no model. Includes the known-item pin candidate |
| `GET /api/annotate` (SSE) | new | Tier 1–2 jobs, streamed, guarded, cached; passages from a short-lived cache keyed by search id |
| `GET /api/similar/{item_id}` | new | Item-level vector plus vocabulary pearl growing |
| `POST /api/export` | new | CSL in the renderer; BibTeX, RIS, pathfinder server-side |
| `POST /api/zotero/collection` | new | Write-back, feature-detected |
| `provider_manager.complete_json()` | new | The one structured-output helper |
| `embed_utils`: entailment check | new | Small NLI model, lazy, CPU, tier 1 only |
| `_index_one` / `_chunk_metadata` | adapt | Contextual header; item key and DOI; bump metadata version |
| `metadata_extractor.py` | keep | Regex path is tier 0; LLM path via `complete_json()`, validated against library vocab |
| `embed_utils.rerank_passages` | keep | Add per-model calibration parameters |
| `vector_db.py` | keep | Add metadata-only query; trigram later |
| `profiles/{id}/sessions` | reuse | Query-log entries in the same blob; old chat sessions exported to JSON once, then dropped |
| `query_condenser.py`, conversation_store trimming, hybrid message builders, ResponseValidator meta-response checks | legacy mode | Kept for the legacy chat mode; deleted when the toggle is retired |
| `academic_prompts.py` | shrink | Six short job prompts; keep provider-specific system prompt handling |

### Frontend

| Piece | Fate | Detail |
|---|---|---|
| `AppShell` | adapt | Left = `QueryDesk`, main = `Bibliography`, right = `Evidence`; Library and Model panels to the top nav; CSS grid stays |
| `SearchSettingsContext` | keep | Persist per query-log entry |
| `ResponseSelectionContext` | rename | Item selection as a set |
| `SnippetsPanel` | adapt | Becomes `Evidence`: highlight, pin, merged view, open at page |
| `SourcesPanel` | adapt | Becomes the bibliography row list |
| `types/session.ts` | keep | Add `band`, `itemKey`, `extract`, `note`, `pinned` |
| `useChat`, `ChatContext`, `ChatView`, `MessageBubble`, `PromptScaffoldingPanel` | legacy mode | Behind Settings → Interface; deleted when the toggle is retired |

### Search response shape

```json
{
  "search_id": "q_8f3a…",
  "query": "how do platform workers organise collectively?",
  "scope": { "year_min": 2015, "tags": ["Labour"], "extracted": ["year_min"] },
  "known_item": null,
  "items": [
    { "item_id": "4821", "item_key": "QX7PL2M4", "rank": 1, "band": "strong",
      "citation": { "authors": "Woodcock, J.; Graham, M.", "year": 2020,
                    "title": "The Gig Economy", "container": "Polity", "doi": null },
      "extract": { "text": "couriers used WhatsApp groups to organise log-offs…", "page": 118 },
      "note": null,
      "passages": [ { "text": "…", "page": 118, "band": "strong", "chunk_idx": 41 } ] }
  ],
  "see_also_count": 6,
  "timing_ms": { "retrieve": 410, "rerank": 820 }
}
```

## 9. Roadmap

### Phase 0 · Spike and measure (~2 weeks)
- Factor `retrieve()` out of `chat()`; chat keeps working during the spike.
- `POST /api/search` with overlap dedupe, MaxP, extracts. Bare list behind a dev flag.
- Test collection v1: 40 queries over a fixture library (20 subject, 12 known-item, 8 author/browse). Pooled results, LLM-judged labels, 15 percent hand-checked, paired per-query comparisons only.
- Prototype contextual headers on a copy of the index; measure the paired delta.
- Measure the fan-out with `llama-server -np 8` and a 4B model on Apple Silicon.

Done when: search under 2 s at 10k chunks with no model; new ranking wins or ties on paired comparison; header delta and latency numbers written down.

### Phase 1 · v0.7 · The catalogue
- Three panels for real: query desk (scope chips, dashed auto-chips, refinement chips, query log); bibliography (bands, "see also" fold, metadata facets, sort); evidence (highlight, pin, open at page).
- Known-item pin with the deterministic detector. Author and journal grouping.
- Contextual headers, item key and DOI at reindex via the metadata version migration.
- Calibration per reranker fitted on the test collection.
- Export: CSL (APA, Chicago, drop-in styles), BibTeX, RIS.
- Chat moved behind Settings → Interface as a legacy mode; the desk is the default.
- README rewritten: scoped claim, prior art, design rationale with sources, "what this app will never do".

Done when: install to exported bibliography with no model and no key, and the README survives a librarian's review.

### Phase 2 · v0.8 · The desk clerk
- `complete_json()` with per-runtime schema modes and one retry.
- Annotate stream: indicative notes behind both guards; corpus-selected also-try; theme labels; LLM scope extraction validated against library vocab.
- Shared-prefix caching and parallel slots; per-job budgets, cancellation, cache.
- The note evaluation (evaluative-temptation set, entailment-scored and hand-scored) across candidate 4B families → the measured allowlist.
- Tier defaults and the "None" provider as a first-class setting.

Done when: 25 notes within the measured budget on an allowlisted 4B model; every shown note passes both guards; no model on the allowlist without a number.

### Phase 3 · v0.9 · The stacks
- Pearl growing (item-level vectors, vocabulary move); metadata-only browse; multi-select and merged evidence.
- Citation chaining with owned items marked; per-user Semantic Scholar key; OpenAlex optional with per-user key.
- Pins with optional Rocchio re-rank; reading lists; pathfinder export.
- Write-back to Zotero collections, feature-detected across Zotero 7–10.
- Tier 2 facets. Trigram keyword index.
- Scripted berrypicking test: 4–5 query trails that must reach a target item set.

Done when: an hour-long review session never needs a retyped query, and the trail test passes in CI.

### Phase 4 · v1.0 · Closing time
- Publish the evaluation: test-collection method, ranking results, and the two measurements nobody has made (do indicative notes hallucinate less than informative ones; does the decomposed pipeline beat one large generation on faithfulness).
- Performance at 100k chunks: paginated bibliography, lazy evidence hydration, batched metadata lookups.
- Accessibility: keyboard through rows and passages, focus order left to right, reduced motion.
- Docs and a "how to use the desk" guide that never says "ask a question".
- Zotero forum launch following community norms: opt-in, local by default, no SQLite writes, no mandatory key.

Done when: no code path asks a model to answer a question, and the write-up is public.

## 10. How we know it is good

**Test collection:** 40 queries in v1, 60 by v0.9 (20 is below the floor at which retrieval experiments discriminate systems; Voorhees and Buckley 2002). Split by intent; known-item must hit at rank 1. Pooled results, LLM-judged relevance (UMBRELA-style) with 10–15 percent human spot-checks (Soboroff 2024 on judge/system circularity). Paired per-query win/loss, never point estimates. Precision@5 cannot regress in CI. Scripted trails for berrypicking features.

**Tests to add:** `test_retrieve.py` (dedupe, MaxP, per-item cap, bands, empty-scope browse); `test_search_api.py` (shape, no provider, extraction merged with manual filters, known-item pin); `test_known_item.py` (author-year, quoted title, DOI, ISBN, false-positive set); `test_complete_json.py`; `test_guards.py` (wrong page, foreign author, low entailment → extract, non-candidate also-try); `test_note_tone.py` (hand-reviewed on every prompt change).

**Targets:** first paint under 2 s at 10k chunks and under 5 s at 100k with no model, plus the measured cost of model query reading when it is on; notes within the Phase 0 measured budget; zero guard failures and zero unlabelled model text shown to users.

## 11. Positioning and visibility

- **The one sentence:** "A reference desk for your Zotero library: ranked sources with the evidence open at the page, no answers, no cloud unless you ask for it."
- **Place, not persona.** Credit the profession's methods; cite them in the README's design-rationale section; the tool does the catalogue's job, not the librarian's.
- **Name the prior art** in the README and the launch post.
- **Lead with what it refuses to do:** answer questions, synthesise papers, send PDFs anywhere, write to the Zotero database behind your back, require an API key.
- **Publish the evaluation** at v1.0.
- **Match the Zotero community's stated trust list:** local-only, bounded database interaction, no mandatory key; no silent SQLite writes, no cloud PDF upload, no forced AI.
- **Studio presence:** an About panel with the Quiet Signals Lab name, other products, and the design-rationale link. No newsletter capture, no telemetry.
- **Licensing:** citeproc-js at arm's length; CSL styles CC BY-SA; Semantic Scholar and OpenAlex with per-user keys and attribution; no API redistribution.

## 12. Risks

- **Friction.** People prefer the less effortful design even when it serves them worse (Buçinca et al. 2021). Absorb with speed, ranking quality and extracts. Cross-document synthesis has visible forum demand; the decision is to leave it out and say why.
- **Convergence.** ZotSeek is nearest; Beaver is one decision away. Durable differentiators are slow to copy: the no-model baseline done well, the design discipline, the evaluation.
- **Maintainer burnout.** Smallest codebase that does the job; delete chat; an allowlist, not a promise to support every model.
- **Unverified numbers.** ~20 audit citations flagged unverified; all latency figures are extrapolations. Nothing reaches a README until checked or measured.
- **Ranking change** surprises existing users; changelog it; the test collection is the arbiter.
- **Metadata hydration cost.** Batch the endpoint; move item key and DOI into chunk metadata.
- **Small-model extraction over-triggers.** Dashed removable chips; regex floor.

## 13. Reference shelf

Entries marked [NV] were not independently verified by the audit; check before public use.

**Library and information science:** Asher, Duke & Wilson (2013) C&RL 74(5); ACRL (2016) Framework; Bates (1989) Online Review 13(5); Belkin, Oddy & Brooks (1982) J. Doc. 38(2) [NV]; Borgman (1996) JASIS 47(7) [NV]; Cutter (1876); Dervin & Dewdney (1986) RQ 25(4) [NV]; Durrance (1989) LJ 114(7) [NV]; Gers & Seward (1985) LJ 110(18) [NV]; Hearst (2009) *Search User Interfaces*; Hernon & McClure (1986) LJ 111(7); IFLA LRM (2017); ISO 25964; Kuhlthau (1991) JASIS 42(5); Kuhlthau (1993) *Seeking Meaning*; Lown, Sierra & Boyer (2013) C&RL 74(3); Marchionini (2006) CACM 49(4); ANSI/NISO Z39.14; Ranganathan (1931, 1933); RUSA (2023) Behavioral Guidelines; Richardson (2002) LJ 127(7) [NV]; Saracevic (1975) JASIS 26(6), (2007) JASIST 58(13) Parts II–III; Taylor (1968) C&RL 29(3); White & Roth (2009); Yee et al. (2003) CHI.

**Retrieval, models and trust:** Buçinca, Malaya & Gajos (2021) CSCW; Cleverdon (1967); Cohan et al. (2020) SPECTER; Cormack, Clarke & Büttcher (2009) RRF; Dai & Callan (2019) SIGIR; Ding, Facciani et al. (2025) AAAI; Garfield (1955); Harter (1986); Pirolli & Card (1999); Rocchio (1971) [NV]; Soboroff (2024) arXiv:2412.17156; Tang et al. (2024) MiniCheck [NV]; Tombros & Sanderson (1998) SIGIR; Upadhyay et al. (2024) UMBRELA; Vectara FaithBench (2024) and Hallucination Leaderboard; Voorhees & Buckley (2002) [NV]; Magesh et al. (2024) Stanford RegLab.

**Products, communities and film:** Ai2 Paper Finder (2025) and Tay's review; Anthropic contextual retrieval (2024); DEVONthink See Also & Classify; ZotSeek (introfini, 2025–26); Lo et al. (2023) Semantic Reader Project; Pasiak (2026) Scholarly Kitchen; Zotero Forums 2026 AI threads; *Party Girl* (von Scherler Mayer, 1995).
