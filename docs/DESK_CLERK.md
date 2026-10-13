# The desk clerk: small models at the reference desk

The desk clerk is how the reference desk uses language models. It is optional: the
desk ranks, extracts and cites with no model at all. When a model is set up, the
clerk does four small jobs with it and checks every answer before the reader sees
it. This document records the design, the research it rests on, and what was
measured. Code: [`backend/clerk.py`](../backend/clerk.py) (the framework),
[`backend/clerk_jobs.py`](../backend/clerk_jobs.py) (the jobs),
[`backend/query_reader.py`](../backend/query_reader.py) (the reader that needs no
model), [`scripts/eval_clerk.py`](../scripts/eval_clerk.py) (the measurement).
Background: [REFERENCE_DESK_PLAN.md](REFERENCE_DESK_PLAN.md).

## The rule

**The model can only improve on an answer the desk already has.** Every job has a
fallback that needs no model, and the model's answer replaces the fallback only
when it passes the job's guard. When the model is missing, slow, malformed or
wrong, the reader gets the fallback, and the desk records why.

That rule follows from what the research says about small models:

| Finding | Consequence in the design |
|---|---|
| Constrained decoding (JSON schema, grammars) guarantees syntax, never meaning. | Every job has a guard that checks the answer against the job's own input. A valid JSON object can still be wrong. |
| Small models fail on parametric knowledge, not on reading what they are given. | Jobs choose from candidates drawn from the library (enums in the schema) instead of generating names, terms or hierarchies. |
| Retrying after a failed check teaches the model to get past the check, not to be right. | One retry for malformed output, with the parse error. No retry after a guard failure. |
| The best hallucination detectors reach about 50% on hard cases (FaithBench, 2024). | Both guards together are mitigation, not certification. The verbatim extract is the default; a note is an upgrade, always labelled. |
| Local inference is bound by prompt processing; a local server takes one call at a time. | Short prompts with a few plain rules and one example; per-call time limits; work queued in the order the reader looks at it. |
| 4B is the smallest class with evidence for faithful short notes (Qwen3-4B best measured). | Measured models are listed in a register; others are labelled "unmeasured" and still guarded. |

## How a job runs

A `Job` is a prompt, a JSON schema (fixed, or built from the input when the
allowed values depend on it), a guard, a fallback, a token limit, a time limit and
an optional `skip`. `Clerk.run(job, data)` never raises:

1. No model configured → fallback, reason `no_model`.
2. `skip(data)` gives a reason → fallback, reason `not_needed: …`. Used when the
   answer without a model is already complete, so the model is asked only about
   what the library's own data cannot settle.
3. Cached result for (job, model, input) → returned.
4. The call runs on a thread pool under the job's time limit → `timeout`. The
   provider's request timeout closes the connection so a local server stops.
5. Provider error (down, auth, rate limit) → `provider_error`.
6. Parse (thinking blocks and code fences are ignored), repair the two harmless
   slips small models make (a null or missing list is an empty list; a string of
   digits where a whole number is wanted is that number), and validate against
   the schema; one retry with the error → `malformed`.
7. Guard → cleaned answer, or `guard: <why>`.

Hybrid reasoning models think before they answer unless told not to, and a
job's small token budget runs out mid-thought: Qwen3 1.7B returned empty replies
for all ten notes. Ollama receives `think: false`; for servers with an OpenAI API
the clerk appends Qwen3's `/no_think` switch to the system prompt of hybrid
Qwen3 models (not the 2507 Instruct models, which do not think).

The system prompt is shared and short: the clerk describes requests and
documents, never answers questions or states facts about the world, uses only what
it is given, and replies with one JSON object. Temperature is 0.

### Structured output by provider

| Provider | How the schema is sent |
|---|---|
| Ollama | `format` = the schema, `think: false`; repeat penalty 1.0 |
| OpenAI, LM Studio | `response_format` json_schema, strict |
| Mistral, Groq, OpenRouter | `response_format` json_object |
| Anthropic, Google | prompt only |

The prompt itself ends with a one-line template of the reply, built from the
schema (`{"note": "<text>", "page": <one of 112, 118, null>}`), not the schema:
given the raw JSON Schema and no enforcement (mlx_lm.server ignores
`response_format`, as prompt-only providers do), Llama 3.2 3B echoed the schema
back in 8 of 10 note calls. The template is also shorter, which made every call
faster: Qwen3-4B's median query reading went from 5.8 to 5.1 s and its notes from
3.4 to 3.0 s. Repetition and frequency penalties are switched off for JSON: they
penalise the quotes and braces JSON is made of.

## The jobs

### Reading the query (`READ_QUERY`): before the search

Finds the limits in a request: years, author, tags, collections, item types,
exclusions. The topic is what is left.

**The library reader goes first.** `query_reader.read()` matches the request
against the library's own vocabulary (author surnames, tags, collections, item
types) and a set of date phrases, in several languages. It is right about every
phrase it recognises. The model is asked only when the reader leaves a possible
limit in the topic (a date word, a document type, a collection or tag word, an
exclusion marker, or a library author's name); otherwise `skip` declines.

**The model fills gaps, it does not overrule.** The guard merges the model's
reading into the library's: the library wins on every field it filled, and the
model may fill only the fields it left empty. Each value must be tied to a phrase
in the request:

- dates need a date phrase; a stated year may be moved by one ("before 2000" →
  1999) and no further; an upper limit of this year or later is no limit;
- an author needs an authorship phrase ("by X", "X's books", "X has written",
  "X and colleagues", "X on …"): a person the request asks *about* is not an
  author limit;
- a tag must be the one named after "tagged" or "#";
- a collection must share its words with the phrase that names it ("my thesis
  folder"), or share none with the request at all (a loose name such as "thesis"
  for "PhD Research"): "readings from my thesis folder" is not the "Reading group";
- a document type needs a type word used as the thing asked for ("chapters on …",
  "surveillance chapters before 2000"), not inside the topic ("reports of police
  violence", "books as objects");
- an exclusion needs a marker ("not about", "but nothing on", "excluding",
  "leaving out"). Bare "not" and "without" are not markers: "why workers do not
  join unions" and "organising without unions" are about unions.

**The model never writes the topic.** Asked to, a 4B model copied the whole
request back every time while choosing the fields correctly. The topic is the
request with the phrases behind every accepted limit cut out, by the same code
for both readers.

Why this shape, measured on the evaluation set (Qwen3-4B, below): with the model
reading every query and overruling the library reader, 12 of 24 readings were
right against 21 for the library reader alone. The model missed date phrases the
regular expressions catch, wrote "until this year" into open ranges, and read
people the request asked about as authors.

### Indicative note (`NOTE`): after the list

One sentence on what an item's passages say about the search, so the reader can
decide whether to open it. Indicative, not informative or evaluative (ANSI/NISO
Z39.14; annotated-bibliography practice): it says what the passages cover, never
whether they are right. The plan inverts the standard's preference for
informative abstracts on purpose: the reader is one click from the page.

The note replaces the row's extract only when it passes both checks, and it is
always labelled "Clerk's note". The guard:

1. keeps the first sentence, at most 40 words;
2. rejects evaluative words ("important", "convincing", "shows that", "proves");
3. rejects capitalised words and numbers that are not in the title, query or
   passages: the cheapest hallucinations are invented names, places and figures
   ("CNNs" for "CNN" and "MCMC-based" for "MCMC" are not new names);
4. entailment: the note, without its indicative verb ("Describes how"), must be
   entailed (≥ 0.5) by a passage, by all passages together (a note may join
   two), or by a window of three sentences (SummaC, Laban et al. 2022), using
   `cross-encoder/nli-MiniLM2-L6-H768` on the CPU.

Each of the entailment premises exists because of a measurement:

- with the indicative verb left in, faithful notes scored 0.00–0.03: NLI reads
  "Describes …" as a claim about the text, which the passage does not make;
- with each passage alone, notes that join two passages failed (0.01); with the
  passages together they pass (0.97–0.99);
- on real abstracts the joined premise passes the 512-token limit and is cut;
  adding three-sentence windows raised the real-library yield from 18 to 22 notes
  of 30, while no known-bad note scored above 0.34 either way.

DeBERTa-based NLI models fail to load under Python 3.13 with this torch; the
MiniLM model is 316 MB and loads lazily on the first note.

### Also try (`ALSO_TRY`): after the list

Next searches (Bates' berrypicking; pearl growing). Candidates come from the
results' own tags, or from two-word phrases their titles share when the library
has few tags, ordered by how many results carry them. The model only chooses up
to four of them. The fallback is the three most common.

The relation shown (BT, NT, RT, after ISO 25964) comes from the words, not the
model: a term inside the search is broader, one that contains the search is
narrower, anything else is related. In the first measurement the model typed two
of sixteen suggestions wrongly ("Deep learning" as narrower than "adversarial
examples"): hierarchy is world knowledge, which is where small models fail.

### Themes (`THEMES`): after the list

Results are grouped by k-means over title embeddings (three groups from nine
listed items, four from sixteen; fewer are not grouped), and the model names each
group in two to four words. A label must reuse a word from its group's titles or
tags; otherwise, and without a model, the label is the tag most of the group
shares, else its most common title word.

### Order of work

After the list appears, the frontend asks `POST /api/annotate` for the clerk's
work and receives it as newline-delimited JSON as each piece finishes. Work is
queued by what the reader sees first: notes for the top three rows, then the next
searches, then theme labels, then the remaining notes. A new search aborts the
stream, and work that has not started is cancelled.

## Measurement

`scripts/eval_clerk.py` runs every job, with its guard and fallback, against a
configured model over [`backend/tests/fixtures/clerk_eval.json`](../backend/tests/fixtures/clerk_eval.json).
All its text was written for the set; none comes from a real library. The
query-reading cases come in four groups:

- **plain**: phrasings the library reader was written for;
- **beyond**: phrasings it does not handle, where a model can help;
- **trap**: topic words that look like limits, where reading too much is the error;
- **held-out**: written after the guards were tuned on the other three, and not
  tuned on since. This is the honest number.

The first three groups were used to develop the guards, so their scores are
optimistic.

### Results

Apple M1, 16 GB, models in 4-bit through mlx_lm.server, 2026-10-11. Counts of
correct readings, and of notes that passed both checks.

| | Qwen3-4B-Instruct-2507 | Llama 3.2 3B Instruct | Qwen3 1.7B | No model |
|---|---|---|---|---|
| Query reading, all (54) | 53 | 49 | 50 | 42 |
| plain (24) | 24 | 23 | 24 | 23 |
| beyond (10) | 10 | 8 | 9 | 4 |
| trap (6) | 6 | 6 | 6 | 6 |
| **held-out (14)** | **13** | **12** | **11** | **9** |
| Notes (10) | 9 | 10 | 7 | the extract |
| Median time, reading / note | 5.0 / 3.1 s | 3.2 / 2.1 s | 2.3 / 1.3 s | |

The model was asked to read 20 of the 54 queries; the rest were complete
without it. Every model misses "Tsay's textbook on financial time series": the
guard's list of work words has no "textbook", and the held-out set is not tuned
on.

Read by hand, Qwen3-4B's notes were the most precise. Llama's were faithful but
vaguer ("Discusses the effects of working from home on productivity"). Qwen3
1.7B shortened "probably approximately correct" to "probably correct", which the
entailment check let through, and needed the `/no_think` switch to answer at
all. Qwen3-4B-Instruct-2507 is the recommended clerk; the smaller models work,
faster, with more fallbacks.

How the design got here, on the same set with Qwen3-4B: with the model reading
every query and overruling the library reader, 12 of 24 readings were right
against 21 for the library reader alone (see "Reading the query"); the first
note gate passed 5 of 10 faithful notes (see "Indicative note").

Same set through Ollama (Q4_K_M), Apple M1, 16 GB, 2026-10-13. Qwen3 4B here is
the hybrid thinking model with `/no_think` and `think: false`, not the 2507 Instruct.

| | Qwen3 4B (hybrid) | Gemma 3 4B | Llama 3.2 3B | No model |
|---|---|---|---|---|
| Query reading, all (54) | 52 | 52 | 50 | 42 |
| **held-out (14)** | **12** | **12** | **12** | **9** |
| Notes (10) | 10 | 9 | 10 | the extract |
| Median time, reading / note | 4.9 / 3.3 s | 5.9 / 3.7 s | 3.9 / 2.0 s | |

Read by hand: Qwen3 4B and Gemma 3 4B name the specifics (the union's 5,000
members, a two-year out-of-sample forecast); Llama 3.2 3B is faithful but
vaguer ("Reports membership numbers of workers in certain jobs"). Gemma's one
rejected note was a correct but over-compressed account of adversarial
perturbations that the entailment gate did not follow. Any of the three is a
usable clerk through Ollama; Qwen3 4B is the best of them.

Through Ollama the clerk asks for `keep_alive: 30m`, so the model stays loaded
between searches (Ollama's default unloads it after five minutes, and reloading
a 4B model costs several seconds on the next job). Ollama answers one request
at a time unless `OLLAMA_NUM_PARALLEL` is set; the annotate stream sends two jobs
at once, so `OLLAMA_NUM_PARALLEL=2` lets notes and next searches run together.

### On a real library

Run on a throwaway index of 599 items (Zotero abstracts) with Qwen3-4B on an
Apple M1 (16 GB, MLX 4-bit). Only counts are recorded here.

- Notes: 22 of 30 passed both checks across six queries (top five listed items
  each); the other eight kept their extract. Hand review of the rejected notes
  found them mostly faithful but condensed further than the gate can follow: the
  gate trades yield for precision, as intended.
- Query reading: a request of the form "anything *author* has written on
  *topic*", naming one of the library's authors, was read as that author and
  topic in 3.6 s warm. The first call after the model server started timed out
  at the 8 s limit and fell back to the library reading. A request naming "my
  thesis folder" needed no model: the library reader matched the library's
  thesis collection.

## The measured-model register

[`backend/clerk_models.json`](../backend/clerk_models.json) lists models the desk
has measured, with the date, hardware and per-job results; `GET /api/desk/model`
reports whether the configured model is on it, and the desk labels others
"unmeasured". Model names are compared across runtimes after normalising
(`mlx-community/Qwen3-4B-Instruct-2507-4bit`, `qwen3:4b-instruct-2507-q4_K_M` and
`qwen3-4b-instruct-2507` are the same model). To add a model:

```
python scripts/eval_clerk.py --provider ollama --model qwen3:4b-instruct-2507 \
    --hardware "Apple M2, 24 GB" --record
```

Read the printed notes before recording: the guards check faithfulness, not
whether a note is useful.

## Known limits

- The evaluation set is small and synthetic, and was written by the same hand as
  the guards. The held-out group has fourteen cases.
- The NLI model was trained on English. Notes on passages in other languages will
  mostly fail the entailment check and keep the extract; query reading is
  multilingual for date phrases only.
- The first model call after a local server starts can exceed the reading time
  limit; the desk then uses the library reading for that search.
- Measured on one machine (Apple M1, 16 GB) through one runtime (MLX). Latency on
  other hardware is unmeasured.

## Settings

`deskReadQuery`, `deskReadTimeout` (seconds, default 8), `deskNotes`,
`deskAlsoTry`, `deskThemes`, all on by default and switchable in the desk's
Clerk room. Each needs a model to do more than its fallback.

`deskClerkCloud`, off by default: the clerk uses a cloud provider only when it is
on. A key set up for legacy chat is not consent to send a query and up to thirty
items' passages to that provider on every search. Local models need no switch.

With a local model, the annotate stream uses one worker: a local server answers
one call at a time, so a second worker only queues work that the next search's
query reading would wait behind. Cloud providers get three.
