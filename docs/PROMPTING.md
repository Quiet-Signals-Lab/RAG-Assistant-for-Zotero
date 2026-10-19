# How the chat prompts a model

The chat answers from passages in your library, for literature review and discovery:
what the library holds on a question, what each source argues, where sources differ, and
what the retrieved passages leave uncovered. It is not a general assistant. Nothing here
needs configuring.

## What the model is told

One system prompt of about 300 words (`backend/academic_prompts.py`), with nine numbered
rules in order of importance:

1. Every claim carries the number of its source, even when the author is named. Only
   numbers that appear in the message may be used. Pages go in words, (p. 12), never in
   brackets.
2. Say only what the passages say; they are excerpts, often cut mid-sentence. Quote a
   short phrase with its page when the wording matters.
3. When the passages do not answer the question, or only part of it, say so. Do not fill
   the gap, and do not cite earlier answers as evidence.
4. Leave out passages that do not bear on the question.
5. When a passage reports another author's view, say so ("as [2] summarises Damasio"),
   and offer such works as leads.
6. Where sources disagree, say so and cite each side.
7. Keep inference brief and mark it as the model's own.
8. A topic rather than a question asks for a short overview. "These" sources means the
   sources already discussed.
9. Begin with the answer, in plain prose, as short as the question allows. No headings
   and no reference list: the app shows the sources beside the answer.

Each turn's message gives the question, the passages that matched grouped under their
source (one number per source, not per passage), a one-line key to sources cited earlier
whose passages are not in this turn, and where the passages came from: the whole library,
the items chosen in search, the part matching filters, or the sources discussed so far.

## Citation numbers

A number names one source for the whole conversation. The backend keeps the numbering per
session, so [2] in the first answer is the same paper as [2] in the fifth, and the
interface links each number to that source. References are formatted by the app from
Zotero's metadata, never written by the model.

A follow-up that refers back ("which of these is the earliest?") searches the sources
already discussed first, and the whole library only when they hold nothing on it.

## Why the prompt is short

Small local models follow a prompt only when it is short, the rules are numbered, and
nothing optional is mentioned: a 377-word draft that mentioned tables once produced tables
in a third of answers, turned the purpose sentence into section headings, and doubled
answer length. Measured with Gemma 3 4B on the test set through `scripts/eval_chat.py`
(three queries, each as a first question, a follow-up and a scoped question):

| Across 9 answers | 377-word draft | shipped prompt |
|---|---|---|
| Answers citing a number that names no source | 3 | 1 |
| Answers with headings or tables | 3 | 0 |
| Median share of sentences with a citation | 0.25 to 0.5 | 0.5 to 1.0 |
| Median words, first question | 359 | 101 |

## Checking it

`python scripts/eval_chat.py --limit 3 --show` runs against the app on `127.0.0.1:8000`
with the active model and prints each answer with its checks: unknown citation numbers,
numbers that changed source between turns, cited-sentence share, reference lists, pages in
brackets, headings or tables, and length. Faithfulness to the passages still needs a
human read of the answers it prints.

## Generation settings

`AcademicGenerationParams` in `backend/academic_prompts.py`: temperature 0.35, 2000 tokens,
`top_p` 0.9, `top_k` 50, repetition penalty 1.15 (applied per provider in
`backend/model_providers/`), and a separate preset for session titles.
