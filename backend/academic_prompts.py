"""
The chat's prompts: one system prompt and one message shape for every turn.

A turn's message carries the question, the passages that matched it (numbered
with the session's citation numbers), a one-line key to sources cited earlier in
the conversation whose passages are not in this turn, and the part of the
library the passages came from. The model is told nothing about structure: the
answer takes the shape the question needs, and references are the
application's job, not the model's.
"""

import re
from typing import Dict, List, Optional


class AcademicPrompts:
    SYSTEM_PROMPT = """You help a researcher see what their own Zotero library says about a question, so they can find and weigh sources. You work only from the passages in the messages. You do not explain topics from general knowledge, give advice, or write on the researcher's behalf.

Each message gives the passages that matched, grouped under their source and numbered [1], [2] and so on, and says what part of the library they come from. A number names the same source for the whole conversation.

Rules

1. Every claim carries the number of the source it comes from, even when you name the author: "Ging et al. argue that ... [1]". Use only numbers that appear in the message. Give pages in words, (p. 12), never in brackets.
2. Say only what the passages say. They are excerpts, often cut mid-sentence: do not infer an author's conclusion from a fragment. Quote a short phrase, with its page, when the wording matters.
3. When the passages do not answer the question, or only part of it, say so plainly. Do not fill the gap, and do not cite your own earlier answers.
4. Leave out passages that do not bear on the question, without mentioning them.
5. When a passage reports another author's view, say so: "as [2] summarises Damasio". You may point to such a work as a lead, naming the passage that mentions it.
6. Where sources disagree, say so and cite each side.
7. Keep your own inference brief and mark it as yours: "taken together, these suggest".
8. A topic rather than a question asks for a short overview of what the passages say about it. "These" or "those" sources means the sources already discussed.
9. Begin with the answer, in plain prose, as short as the question allows, in the language of the question. No headings and no reference list: the application shows the sources beside the answer."""

    @classmethod
    def get_system_prompt(cls, provider_id: Optional[str] = None) -> str:
        """The system prompt; `provider_id` is accepted for older callers and ignored."""
        return cls.SYSTEM_PROMPT

    @staticmethod
    def _source_line(s: Dict) -> str:
        bib = f"{s.get('authors') or 'Unknown'} ({s['year']})" if s.get("year") else (s.get("authors") or "Unknown")
        return f"{bib}. {s.get('title') or 'Untitled'}"

    @classmethod
    def build_turn_message(cls, question: str, snippets: List[Dict], scope: str, earlier_sources: Optional[List[Dict]] = None) -> str:
        """
        The user message for one turn.

        `snippets`: this turn's passages, each with citation_id, title, authors, year, page, snippet.
        `scope`: where they come from, in words ("your whole library", "the 3 items you chose").
        `earlier_sources`: sources cited earlier in the session that have no passage in this turn,
        each with id, title, authors, year; listed so their numbers keep meaning something after
        the history is trimmed.
        """
        parts = [question.strip()]
        if snippets:
            # One heading per source, its passages beneath: the number names the source, not the passage.
            by_source: Dict = {}
            for s in snippets:
                by_source.setdefault(s.get("citation_id", "?"), (s, []))[1].append(s)
            blocks = []
            for cid, (first, group) in by_source.items():
                lines = [f"({'p. ' + str(s['page']) if s.get('page') else 'no page'}) {s.get('snippet', '')}" for s in group]
                blocks.append(f"[{cid}] {cls._source_line(first)}\n" + "\n".join(lines))
            parts.append(f"Passages that matched, from {scope}. They are excerpts.\n\n" + "\n\n".join(blocks))
        else:
            parts.append(
                f"No passage in {scope} matched this question. Say so. If passages given earlier in this "
                "conversation answer it, answer from those, citing them by number."
            )
        if earlier_sources:
            key = "\n".join(f"[{s['id']}] {cls._source_line(s)}" for s in earlier_sources)
            parts.append("Sources cited earlier in this conversation, for their numbers:\n" + key)
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def normalise_citations(text: str) -> str:
        """"[1, 2]" and "[1,2]" become "[1][2]": one number per bracket, as the interface links them."""
        return re.sub(r"\[(\d+(?:\s*,\s*\d+)+)\]", lambda m: "".join(f"[{n}]" for n in re.split(r"\s*,\s*", m.group(1))), text)

    @classmethod
    def build_session_title_prompt(cls, user_question: str, assistant_response: str) -> str:
        """Generate a concise title for a research session."""
        return f"""Generate a concise, descriptive title (3-8 words) for this research conversation.
Focus on the main topic or research question being explored.

**User Question:** {user_question[:300]}

**Assistant Response:** {assistant_response[:300]}

Requirements:
- 3-8 words maximum
- Capture the core research topic
- No quotes or punctuation
- Academic tone

**Title:**"""


class AcademicGenerationParams:
    """Generation presets: the answer, and the session title."""

    STANDARD = {"temperature": 0.35, "max_tokens": 2000, "top_p": 0.9, "top_k": 50, "repeat_penalty": 1.15}
    TITLE = {"temperature": 0.7, "max_tokens": 30, "top_p": 0.9, "top_k": 50, "repeat_penalty": 1.1}

    @classmethod
    def get_params(cls, mode: str = "standard") -> Dict:
        return cls.TITLE if mode == "title" else cls.STANDARD


__all__ = ["AcademicPrompts", "AcademicGenerationParams"]
