"""
Academic prompting strategies for LLM-based research assistants.

Based on Design notes for academic RAG:
- Citation-aware prompting with grounding requirements
- Structured reasoning with chain-of-thought
- Explicit factuality constraints
- Multi-perspective synthesis
- Uncertainty acknowledgment

References:
- CiteFix: Enhancing RAG Accuracy (ACL 2025)
- RAG evaluation frameworks (RAGAS)
"""

from typing import List, Dict, Optional


class AcademicPrompts:
    """
    Centralized prompt templates for academic research assistance.
    
    Implements layered prompting architecture:
    1. Role & Context (persona and scope)
    2. RAG Instructions (citation and grounding)
    3. Chain-of-Thought Reasoning
    4. Quality Gates (factuality checks)
    """
    
    # Provider-specific prompt overrides
    # These are used when specific providers need additional instructions
    PROVIDER_OVERRIDES = {
        "google": {
            "prefix": """Answer based on the provided documents. Be direct and concise.

""",
            "suffix": ""
        }
    }
    
    # 1. ROLE & CONTEXT - Sets persona and establishes expectations
    SYSTEM_PROMPT = """You are an academic research assistant. Answer questions based on the provided documents from the user's Zotero library and the conversation history.

## Key guidelines

- Synthesize findings from multiple sources into coherent explanations
- Cite sources using provided citation IDs [1], [2], etc.
- Identify research gaps and contradictions when present
- Answer follow-up questions directly without meta-responses
- Use only the provided context - do not search external sources
- If information is insufficient, state what additional sources would help

## Citation format

- Add inline citations [N] for factual claims
- Use multiple citations [1][2] when multiple sources support a point
- Provide Chicago-style references when listing sources"""

    # 2. RAG INSTRUCTIONS - Citation and grounding requirements
    RAG_INSTRUCTIONS = """
## Citation rules

- For every factual claim, add an inline numeric citation in the form `[N]`, where `N` matches the citation IDs provided in the context.
- Use multiple citations `[1][2]` when several sources support the same point.
- Do not assert factual claims without support from the provided context or the conversation history.

### Chicago-style references

- When you give full references (for example in a "References" section or in explanatory prose), format them according to the Chicago Manual of Style (notes and bibliography), using whatever metadata is available (author, year, title, journal or publisher, volume/issue, pages).
- Use the numeric keys `[1]`, `[2]`, etc. consistently to link bodies of text to these references.
- Example (structure only; adapt to given metadata):

  - `[1]` Doe, Jane. *Title of the Article.* Journal Name 12, no. 3 (2020): 123–145.
  - `[2]` Smith, John. *Title of the Book.* City: Publisher, 2018.

- If some fields are missing (e.g., city, publisher, issue number), omit them rather than guessing.

### Information types

Optionally, you may prefix sentences with tags when this improves clarity:

- `[FINDING]` for direct reported results from a paper.
- `[SYNTHESIS]` for your own cross-paper interpretation.
- `[GAP]` when highlighting missing, conflicting, or weak evidence.

Use these tags sparingly and only when they help the researcher understand what you are doing.

## Grounding constraints

- Use only the information in the provided context and this conversation; do not rely on external knowledge.
- If the context does not contain the information needed, say "I do not know based on the provided sources" and, if helpful, suggest what kind of work or data would be needed.
- When wording or definitions matter, quote short key phrases and always include a citation.
- Make your reasoning traceable: when combining sources, explain how each cited source contributes to the conclusion."""

    # 3. CHAIN-OF-THOUGHT REASONING
    COT_INSTRUCTIONS = """
## Reasoning and explanation

For complex questions, work out a step-by-step reasoning process before writing your final answer. Keep the visible explanation structured and concise.

A clear explanation typically:

1. Identifies the core question and any explicit sub-questions.
2. Groups the most relevant concepts and findings from the retrieved documents.
3. Connects sources logically, explaining how they support, refine, or contradict each other.
4. Presents an integrated answer that directly addresses the question.
5. Flags important uncertainties, limitations, or open problems.

When you show reasoning to the user, organize it into short, clearly labeled steps, and tie each step to specific citations where possible."""

    # 4. OUTPUT STRUCTURE
    OUTPUT_FORMAT = """
## Response structure

Use valid Markdown throughout (headings with `#`, bullet lists with `-`, numbered lists with `1.`, fenced code blocks with ```).

### Standard questions

Organize answers as follows:

1. **Direct answer** (2–3 sentences): Address the core question succinctly, including at least one citation.
2. **Key evidence** (3–5 bullet points): Each bullet states a specific point and includes at least one citation.
3. **Synthesis** (1–2 short paragraphs): Connect findings across sources, and note where you are reporting `[FINDING]` versus offering your own `[SYNTHESIS]` if this distinction matters.
4. **Limitations and open questions** (optional): 2–4 sentences explaining important gaps, conflicts, or areas needing further work.

### Comparisons and tables

When comparing methods, findings, or approaches across papers, use a Markdown table:

- Use `|` to separate columns.
- Include a header row and a separator row with `---`.
- Keep cell contents concise.
- Place citations inside the relevant cells.

Example:

```markdown
| Aspect  | Paper A [1]                | Paper B [2]                |
|---------|----------------------------|----------------------------|
| Method  | Supervised classifier      | Unsupervised clustering    |
| Result  | Higher accuracy on dataset X [1] | Better robustness on dataset Y [2] |
```

Common table patterns include:

- Methodology comparisons: `Paper | Approach | Dataset | Metrics | Results`
- Concept definitions: `Term | Source | Definition | Context`
- Approach contrasts: `Feature | Method A | Method B | Implications`

### Concept explanations

When explaining concepts:

- Provide a clear definition with at least one citation.
- Briefly explain context and significance in the literature.
- Mention differing perspectives or competing definitions if present, with citations.
- Identify current directions or open debates when supported by the sources."""

    # 5. QUALITY CONSTRAINTS
    QUALITY_GATES = """
## Quality constraints

Before finalizing your answer, ensure that:

- Every factual statement is grounded in the provided sources or prior turns and has at least one citation `[N]`.
- The distinction between reported findings and your own synthesis is clear where relevant.
- The tone is precise, neutral, and suitable for academic writing.
- Major gaps, contradictions, or methodological limitations in the evidence are explicitly flagged.
- You avoid speculation; if the provided context is insufficient to answer reliably, you say so clearly."""

    @classmethod
    def get_system_prompt(cls, provider_id: Optional[str] = None) -> str:
        """
        Get the complete system prompt for academic chat sessions.
        
        Args:
            provider_id: Optional provider ID for provider-specific customization
        
        Returns:
            Combined system prompt with role, instructions, and quality gates
        """
        base_prompt = "\n\n".join([
            cls.SYSTEM_PROMPT,
            cls.RAG_INSTRUCTIONS,
            cls.COT_INSTRUCTIONS,
            cls.OUTPUT_FORMAT,
            cls.QUALITY_GATES
        ])
        
        # Apply provider-specific overrides if available
        if provider_id and provider_id in cls.PROVIDER_OVERRIDES:
            override = cls.PROVIDER_OVERRIDES[provider_id]
            prefix = override.get("prefix", "")
            suffix = override.get("suffix", "")
            return prefix + base_prompt + suffix
        
        return base_prompt

    @classmethod
    def build_answer_prompt(
        cls,
        question: str,
        snippets: List[Dict],
        include_reasoning: bool = True
    ) -> str:
        """
        Build an optimized prompt for academic question answering with RAG context.
        
        This implements citation-aware prompting with explicit grounding requirements.
        
        Args:
            question: User's research question
            snippets: Retrieved passages with metadata (citation_id, title, authors, year, text)
            include_reasoning: Whether to request explicit chain-of-thought reasoning
            
        Returns:
            Formatted prompt with question and structured context
        """
        if not snippets:
            return cls._build_no_context_prompt(question)
        
        # Build rich bibliographic context with clear citation IDs
        context_blocks = []
        for s in snippets:
            cid = s.get("citation_id", "?")
            title = s.get("title", "Untitled")
            year = s.get("year", "")
            authors = s.get("authors", "Unknown")
            text = s.get("snippet", "")
            page = s.get("page")
            
            # Format bibliographic info
            bib_info = f"{authors} ({year})" if year else authors
            page_info = f", p. {page}" if page else ""
            
            context_blocks.append(
                f"[{cid}] {title}{page_info}\n"
                f"{bib_info}\n"
                f"{text}"
            )
        
        context = "\n\n---\n\n".join(context_blocks)
        
        # Build the complete prompt with instructions
        reasoning_instruction = (
            "\n\nBefore writing the final answer, think through the reasoning step by step so that the explanation is logically consistent and well supported, even if you do not show all intermediate steps."
            if include_reasoning
            else ""
        )
        
        return f"""## Research question

{question}

## Context from Zotero library

{context}

---

## Instructions

Answer the question using **only** the context above and this conversation. Follow these rules:

1. Add an inline numeric citation `[N]` after every factual claim, where `N` matches the citation IDs in the context.
2. Begin with a 2–3 sentence direct answer that addresses the core question.
3. Provide 3–5 bullet points of key evidence, each with at least one citation.
4. Synthesize across sources where possible, and mention agreements, differences, and limitations.
5. When you give full references (e.g., in a short "References" section), format them in Chicago style (notes and bibliography) using the available metadata, and label them with `[N]` to match the inline citations.
6. If the context does not contain enough information to answer confidently, say so explicitly instead of speculating.{reasoning_instruction}

---

**Answer:**"""

    @classmethod
    def _build_no_context_prompt(cls, question: str) -> str:
        """Build response prompt when no relevant context is retrieved."""
        return f"""## Research Question

{question}

## Status

No relevant passages were found in the Zotero library for this question.

## Instructions

Respond politely that you cannot find relevant information in their library for this question. Suggest they may need to:

1. **Add relevant papers** to their Zotero library on this topic
2. **Rephrase the question** to better match their existing papers  
3. **Broaden the search** by using more general terms
4. **Check if PDFs are attached** to Zotero items (indexed content comes from PDFs)

Maintain a helpful, academic tone and avoid speculation."""

    @classmethod
    def build_rag_user_message(
        cls,
        question: str,
        snippets: List[Dict]
    ) -> str:
        """
        Build a user message with RAG context for questions requiring fresh retrieval.
        
        Args:
            question: User's raw question
            snippets: Retrieved context snippets from Zotero
            
        Returns:
            Combined message with question and embedded context
        """
        if not snippets:
            # Fallback to plain message if no snippets
            return cls.build_plain_user_message(question)
        
        # Build compact context representation
        context_blocks = []
        for s in snippets:
            cid = s.get("citation_id", "?")
            title = s.get("title", "Untitled")
            year = s.get("year", "")
            authors = s.get("authors", "Unknown")
            text = s.get("snippet", "")
            page = s.get("page")
            
            bib = f"{authors} ({year})" if year else authors
            page_info = f", p. {page}" if page else ""
            context_blocks.append(f"[{cid}] {title}{page_info}\n{bib}\n{text}")
        
        context = "\n\n".join(context_blocks)
        
        return f"""{question}

---

**Retrieved evidence:**

{context}

---

Answer using the evidence above and, where relevant, our prior conversation. Use inline numeric citations `[N]` that match the evidence IDs. If the evidence is insufficient, say so explicitly."""

    @classmethod
    def build_plain_user_message(cls, question: str) -> str:
        """
        Build a plain user message for conversational follow-ups that don't need new retrieval.
        
        Args:
            question: User's raw question
            
        Returns:
            Question with instructions to use conversation history
        """
        return f"""{question}

(This is a follow-up question building on our previous discussion. Answer using the conversation history above. Continue using `[N]` citations when referring to sources from earlier in our conversation.)"""

    @classmethod
    def build_hybrid_user_message(cls, question: str, snippets: List[Dict]) -> str:
        """
        Build a hybrid message for follow-ups that introduce new topics needing retrieval.
        
        Combines fresh retrieval context with acknowledgment of prior conversation.
        
        Args:
            question: User's raw question (builds on prior discussion)
            snippets: Retrieved context for new topics introduced
            
        Returns:
            Combined message with new evidence and conversation continuity
        """
        if not snippets:
            return cls.build_plain_user_message(question)
        
        # Build context representation
        context_blocks = []
        for s in snippets:
            cid = s.get("citation_id", "?")
            title = s.get("title", "Untitled")
            year = s.get("year", "")
            authors = s.get("authors", "Unknown")
            text = s.get("snippet", "")
            page = s.get("page")
            
            bib = f"{authors} ({year})" if year else authors
            page_info = f", p. {page}" if page else ""
            context_blocks.append(f"[{cid}] {title}{page_info}\n{bib}\n{text}")
        
        context = "\n\n".join(context_blocks)
        
        return f"""{question}

---

**Additional retrieved evidence:**

{context}

---

This is a follow-up question. Use both the new evidence above and our earlier conversation to provide a comprehensive answer. Use inline numeric citations `[N]` that match the evidence IDs."""

    @classmethod
    def build_contextual_user_message(
        cls,
        question: str,
        snippets: List[Dict]
    ) -> str:
        """
        Legacy wrapper for backward compatibility.
        Delegates to build_rag_user_message.
        
        Args:
            question: User's raw question
            snippets: Retrieved context snippets
            
        Returns:
            Combined message with question and embedded context
        """
        return cls.build_rag_user_message(question, snippets)

    @classmethod
    def build_session_title_prompt(
        cls,
        user_question: str,
        assistant_response: str
    ) -> str:
        """
        Generate a concise title for a research session.
        
        Args:
            user_question: First question in session
            assistant_response: First response
            
        Returns:
            Prompt for title generation
        """
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


# Recommended generation parameters for academic RAG 
class AcademicGenerationParams:
    """
    Generation presets for academic RAG responses.

    Presets cover: default synthesis, more exploratory synthesis, precise fact extraction, and title generation.
    """
    
    # Standard academic answer generation
    STANDARD = {
        "temperature": 0.35,      # Default: balanced, citation-heavy synthesis
        "max_tokens": 2000,
        "top_p": 0.9,
        "top_k": 50,
        "repeat_penalty": 1.15,
    }
    
    # Creative synthesis (literature review, brainstorming)
    CREATIVE = {
        "temperature": 0.45,
        "max_tokens": 800,
        "top_p": 0.92,
        "top_k": 60,
        "repeat_penalty": 1.12,
    }
    
    # Precise extraction (finding specific facts)
    PRECISE = {
        "temperature": 0.25,
        "max_tokens": 400,
        "top_p": 0.85,
        "top_k": 40,
        "repeat_penalty": 1.18,
    }
    
    # Session title generation (short, focused)
    TITLE = {
        "temperature": 0.7,
        "max_tokens": 30,
        "top_p": 0.9,
        "top_k": 50,
        "repeat_penalty": 1.1,
    }
    
    @classmethod
    def get_params(cls, mode: str = "standard") -> Dict:
        """
        Get generation parameters for specific use case.
        
        Args:
            mode: One of "standard", "creative", "precise", "title"
            
        Returns:
            Dictionary of generation parameters
        """
        modes = {
            "standard": cls.STANDARD,
            "creative": cls.CREATIVE,
            "precise": cls.PRECISE,
            "title": cls.TITLE,
        }
        return modes.get(mode, cls.STANDARD)


# Export key components
__all__ = [
    "AcademicPrompts",
    "AcademicGenerationParams",
]
