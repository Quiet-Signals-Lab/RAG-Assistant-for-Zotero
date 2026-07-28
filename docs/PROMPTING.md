# Prompting & Generation

RAG Assistant uses a citation-aware academic prompting system. It works
automatically — no configuration, re-indexing, or query changes needed. This
page explains what it does and how to tune it.

## What you get

- **Every claim is cited** inline with `[N]` markers tied to retrieved sources.
- **Facts vs. analysis are distinguished** — direct findings from papers vs. the
  assistant's own synthesis across them.
- **Gaps are acknowledged** — when the retrieved documents don't cover something,
  the answer says so instead of inventing an answer.
- **Structured responses**: direct answer (2-3 sentences) → key evidence (cited
  bullets) → synthesis across sources → limitations.

Example:

> Recent research identifies three primary impact categories [1][2]:
> - Temperature increases of 1.2°C have accelerated ecosystem disruption [1]
> - Ocean acidification up 30%, threatening marine biodiversity [2][3]
>
> **Synthesis:** Sources [1] and [2] agree on warming magnitude but differ on
> regional impacts. **Limitations:** the documents don't address adaptation policy.

## Tuning generation

Presets live in `backend/academic_prompts.py` (`AcademicGenerationParams`). Fetch
one with `AcademicGenerationParams.get_params("standard")`:

| Preset | temp | max_tokens | Use for |
|---|---|---|---|
| `standard` (default) | 0.35 | 600 | Academic Q&A — balances factuality and natural synthesis |
| `creative` | 0.45 | 800 | Literature reviews, brainstorming |
| `precise` | 0.25 | 400 | Specific fact extraction |

Rationale for the defaults: temp 0.2-0.3 causes citation/phrase repetition in
academic content; 0.35-0.4 is the sweet spot; above 0.5 hallucinations spike.
`top_p=0.9` suppresses low-probability hallucinations, `top_k=50` keeps technical
vocabulary diverse, and a repetition penalty (`repeat_penalty=1.15` for Ollama,
`frequency_penalty=0.3` for OpenAI-compatible providers) stops
"as [1] states, [1] shows…" loops. These are applied per-provider in
`backend/model_providers/`.

## Prompt structure

The system prompt (in `academic_prompts.py`) is layered: role/context →
RAG grounding rules (mandatory citations, `[FINDING]`/`[SYNTHESIS]`/`[GAP]`
distinctions) → chain-of-thought reasoning → output structure → a quality-gate
checklist that tells the model to say "I don't know" when evidence is thin.

## Troubleshooting

- **Responses longer than before** — expected; capped at 600 tokens for academic
  depth. Lower `max_tokens` in the `standard` preset if you want them shorter.
- **Model repeating citations** — update your model (`ollama pull <model>`); the
  repetition penalties already mitigate this.

## Background

Design is grounded in citation-accuracy research (notably CiteFix, ACL 2025 —
~80% of RAG "hallucinations" are citation mismatches, not fabricated facts) and
citation-aware tools like Perplexity and Consensus. All changes are backward
compatible; generation params can be overridden per call.
