"""
Query Condensation for Multi-Turn Conversational RAG.

Converts context-dependent follow-up questions into standalone queries
suitable for vector database retrieval.

Based on Perplexity-style conversational RAG architecture:
- Isolates retrieval logic from conversation logic
- Maintains semantic fidelity to original intent
- Prevents retrieval of irrelevant context
"""

from typing import List
from backend.model_providers import Message, ProviderManager


class QueryCondenser:
    """
    Condenses follow-up questions into standalone queries using conversation history.
    
    This is the critical component for multi-turn RAG systems. Without it:
    - Follow-ups like "Is there overlap?" retrieve wrong documents
    - Anaphoric references ("it", "that approach") lose context
    - Comparative questions fail to identify all comparison targets
    
    With condensation:
    - "Is there overlap?" → "Is there overlap between multi-task learning and causal approaches?"
    - "How does it work?" → "How does multi-task learning in NLP work?"
    - "What about X?" → "What about X in relation to [previous topic]?"
    """
    
    # Prompt for query condensation
    # Critical: This must NOT trigger "I'm ready" responses
    # It asks for EXTRACTION, not new instructions
    CONDENSE_PROMPT = """You are converting a follow-up question into a standalone question by incorporating relevant context from the conversation history.

## Task

Given a conversation history and a follow-up question, rephrase the follow-up into a standalone question that:
1. **Replaces pronouns** (it, they, that, these) with specific nouns
2. **Includes implicit context** needed to understand the question
3. **Maintains the original intent** exactly
4. **Is suitable for semantic search** (clear, self-contained)

## Rules

- **Output ONLY the standalone question** - no explanations, no preamble
- **Keep the question format** - if input is a question, output is a question
- **Preserve key terms** from the follow-up exactly
- **Don't add information** not implied by the history
- **Be concise** - only add necessary context

## Examples

**Conversation:**
User: What is multi-task learning in NLP?
Assistant: Multi-task learning (MTL) in NLP is a training paradigm where...

**Follow-up:** Is there an overlap with causal approaches?
**Standalone:** Is there an overlap between multi-task learning in NLP and causal inference approaches?

---

**Conversation:**
User: How does BERT handle contextualized embeddings?
Assistant: BERT generates contextualized embeddings through...

**Follow-up:** What about GPT?
**Standalone:** How does GPT handle contextualized embeddings?

---

**Conversation:**
User: What are the main challenges in few-shot learning?
Assistant: The main challenges include limited training data...

**Follow-up:** Can you elaborate on the data efficiency issue?
**Standalone:** Can you elaborate on the data efficiency challenges in few-shot learning?

---

Now do the same for the conversation below."""

    def __init__(self, provider_manager: ProviderManager):
        """
        Initialize query condenser with LLM provider.
        
        Args:
            provider_manager: Configured LLM provider for condensation
        """
        self.provider_manager = provider_manager
    
    def condense_query(
        self, 
        query: str, 
        conversation_history: List[Message],
        max_history_chars: int = 1500
    ) -> str:
        """
        Condense a follow-up query into a standalone query using conversation history.
        
        Args:
            query: User's follow-up question (may contain pronouns, implicit references)
            conversation_history: Recent conversation messages (system, user, assistant)
            max_history_chars: Maximum characters of history to include (default 1500)
            
        Returns:
            Standalone query suitable for retrieval, or original query if condensation fails
        """
        # Filter out system messages and take only recent history
        relevant_history = [
            m for m in conversation_history 
            if m.role in ["user", "assistant"]
        ][-6:]  # Last 3 turns (6 messages)
        
        # Build compact history representation
        history_lines = []
        total_chars = 0
        for msg in relevant_history:
            prefix = "User:" if msg.role == "user" else "Assistant:"
            # Truncate long messages to avoid context overflow
            content = msg.content[:500] if len(msg.content) > 500 else msg.content
            line = f"{prefix} {content}"
            
            if total_chars + len(line) > max_history_chars:
                break
            history_lines.append(line)
            total_chars += len(line)
        
        if not history_lines:
            # No history - return query as-is
            return query
        
        history_str = "\n".join(history_lines)
        
        # Build condensation prompt
        full_prompt = f"""{self.CONDENSE_PROMPT}

## Conversation History

{history_str}

## Follow-up Question

{query}

## Standalone Question"""
        
        # Call LLM with focused parameters (low temperature for accuracy)
        try:
            messages = [Message(role="user", content=full_prompt)]
            response = self.provider_manager.chat(
                messages=messages,
                temperature=0.2,  # Low temperature for precise extraction
                max_tokens=150,   # Standalone query should be concise
                top_p=0.9,
                top_k=40,
                repeat_penalty=1.1
            )
            
            standalone_query = response.content.strip()
            
            # Validation: ensure we got a reasonable query back
            if len(standalone_query) < 5 or len(standalone_query) > 300:
                print(f"Warning: Condensed query seems malformed ({len(standalone_query)} chars), using original")
                return query
            
            # Remove common artifacts from LLM responses
            standalone_query = standalone_query.strip('"').strip("'")
            if standalone_query.lower().startswith("standalone question:"):
                standalone_query = standalone_query[20:].strip()
            
            # Hallucination guard: if the condensed query shares very few content
            # words with the original, the LLM has wandered off-topic.  Fall back
            # to the original rather than retrieving with a hallucinated query.
            original_words = set(query.lower().split())
            condensed_words = set(standalone_query.lower().split())
            # Remove stopwords that are uninformative for overlap comparison
            stopwords = {"a", "an", "the", "is", "are", "was", "were", "be",
                         "in", "on", "at", "to", "of", "for", "and", "or",
                         "what", "how", "why", "when", "where", "who", "does",
                         "do", "did", "can", "could", "would", "will", "about"}
            orig_content = original_words - stopwords
            cond_content = condensed_words - stopwords
            if orig_content and cond_content:
                overlap = len(orig_content & cond_content) / max(len(orig_content), len(cond_content))
                if overlap < 0.15:
                    print(f"Warning: Condensed query diverged from original (overlap={overlap:.2f}), using original")
                    return query
            
            print(f" Query condensation:")
            print(f"   Original: {query}")
            print(f"   Standalone: {standalone_query}")
            
            return standalone_query
            
        except Exception as e:
            print(f"Query condensation failed: {e}")
            # Fallback to original query
            return query
    
    def should_condense(
        self, 
        query: str, 
        conversation_history: List[Message]
    ) -> bool:
        """
        Determine if a query needs condensation based on heuristics.

        Requires at least one completed exchange (a prior user turn AND a prior
        assistant response) before condensation is attempted.  This prevents
        garbling standalone first-turn questions that happen to contain
        comparison or elliptical language.

        Args:
            query: User's question
            conversation_history: Recent messages
            
        Returns:
            True if query appears to be a follow-up requiring condensation
        """
        # Require a completed exchange: at least one prior user turn AND one
        # prior assistant response.  Checking only user count (old behaviour)
        # triggers on turn 2 even when the assistant hasn't responded yet.
        user_messages = [m for m in conversation_history if m.role == "user"]
        asst_messages = [m for m in conversation_history if m.role == "assistant"]
        if len(user_messages) == 0 or len(asst_messages) == 0:
            return False

        # Strip trailing punctuation before word-boundary tests so that
        # "Can you elaborate on that?" correctly matches the word "that".
        q_raw = query.lower().strip()
        import re as _re
        q = _re.sub(r'[?.!,;:]+$', '', q_raw).strip()

        # Check for anaphoric references (pronouns and determiners that refer
        # to something named earlier in the conversation).
        has_anaphora = any(
            (q.startswith(word + " ") or f" {word} " in q or q.endswith(" " + word))
            for word in ["it", "they", "them", "that", "this", "these", "those", "its", "their"]
        )

        # Formal anaphoric expressions
        has_formal_anaphora = any(phrase in q for phrase in [
            "said", "such", "aforementioned", "the former", "the latter"
        ])

        # Elliptical constructions — the query is syntactically incomplete
        # without the prior conversation context.
        has_ellipsis = any(phrase in q for phrase in [
            "what about", "how about", "also", "additionally",
            "the above", "the previous", "earlier", "you mentioned",
            "as mentioned", "like you said",
            "expand on", "elaborate on", "tell me more",
        ])
        # NOTE: "and" removed from ellipsis list — too broad, fires on
        # legitimate standalone questions like "What are X and Y?"
        # "expand on" / "elaborate on" are safe because we require a completed
        # exchange before triggering, so standalone first-turn questions like
        # "Can you elaborate on cognitive load?" won't match.

        # Condense only when a genuine dependency signal is present.
        # Comparative language alone ("How does Piaget compare to Vygotsky?")
        # is NOT a dependency signal — the query is already self-contained.
        # We previously triggered on (has_comparison AND is_short) which
        # caused false positives on every short comparison question after turn 1.
        should_cond = has_anaphora or has_formal_anaphora or has_ellipsis

        if should_cond:
            print(f"[QueryCondenser] should_condense=True: "
                  f"anaphora={has_anaphora}, formal_anaphora={has_formal_anaphora}, "
                  f"ellipsis={has_ellipsis}")
        
        return should_cond


# Export
__all__ = ["QueryCondenser"]
