# Quick Reference: the RAG Chat pipeline

## TL;DR - The Fix

**Problem**: Follow-up questions cause "I'm ready to begin" responses  
**Root Cause**: Missing query condensation + instructions embedded in follow-up messages  
**Solution**: 3-step pipeline: CONDENSE → RETRIEVE → GENERATE

## Core Control Flow (Per Turn)

```python
def chat(self, query, filter_item_ids=None, session_id=None):
    # STEP 1: Load conversation history
    conversation_history = self.conversation_store.get_messages(session_id)
    user_turns = len([m for m in conversation_history if m.role == "user"])
    is_new_session = (user_turns == 0)
    
    # STEP 2: CONDENSE query if it's a follow-up
    retrieval_query = query  # Default
    if session_id and self.query_condenser.should_condense(query, conversation_history):
        # Convert "Is there overlap?" → "Is there overlap between MTL and causal inference?"
        retrieval_query = self.query_condenser.condense_query(query, conversation_history)
    
    # STEP 3: RETRIEVE using condensed query
    results = self.chroma.query_hybrid_rrf(
        query=retrieval_query,  # ← Use standalone query!
        k=15
    )
    # Re-rank and build snippets...
    
    # STEP 4: BUILD MESSAGES (Critical difference!)
    if is_new_session:
        # First turn: Include RAG context in user message
        user_message = f"{query}\n\n---\n**Evidence:**\n{context}"
    else:
        # Follow-up: ONLY the plain question!
        user_message = query  # ← No embedded instructions!
    
    self.conversation_store.append_message(session_id, "user", user_message)
    messages = self.conversation_store.get_messages(session_id)
    
    # STEP 5: GENERATE answer
    response = self.provider_manager.chat(messages=messages, ...)
    self.conversation_store.append_message(session_id, "assistant", response.content)
    
    return {"summary": response.content, "citations": citations, "snippets": snippets}
```

## Concrete Examples

### Example 1: Why Original Failed

**Turn 2 (BROKEN)**:
```python
# What your code was doing:
user_message = f"""Is there an overlap?

---
**Instructions:**
Answer using the evidence above. Follow these requirements:
1. Cite every claim with [N]
2. Start with a direct answer
3. Provide supporting evidence
...
"""

# LLM reads this and thinks:
# "Oh, these are NEW instructions for me. Let me acknowledge them."
response = "Okay, I understand. I'm ready to begin following these instructions."
```

**Turn 2 (FIXED)**:
```python
# What the code now does:
user_message = "Is there an overlap?"  # Just the question!

# LLM sees conversation history:
# [system] "You are an academic assistant..."
# [user] "What is MTL?" + evidence
# [assistant] "MTL is a training paradigm..."
# [user] "Is there an overlap?"  ← New message

# LLM thinks:
# "This is a follow-up. They're asking about overlap with the topic we just discussed."
response = "Yes, there is significant overlap between MTL and causal inference [1][2]..."
```

### Example 2: Query Condensation in Action

```python
# Conversation History:
# User: "What is multi-task learning in NLP?"
# Assistant: "Multi-task learning (MTL) is a paradigm where..."

# New query (context-dependent):
query = "Is there an overlap with causal approaches?"

# Detection:
should_condense(query, history)  # → True (has "overlap", short, turn > 0)

# Condensation:
standalone = condense_query(query, history)
# → "Is there an overlap between multi-task learning in NLP and causal inference approaches?"

# Retrieval uses standalone query:
results = chroma.query_hybrid_rrf(query=standalone, k=15)
#  Retrieves papers about BOTH MTL AND causal inference

# Without condensation:
results = chroma.query_hybrid_rrf(query="Is there an overlap", k=15)
#  Retrieves random papers containing "overlap"
```

### Example 3: Message Construction Comparison

**Turn 1 (Same for both)**:
```python
messages = [
    Message(role="system", content="You are an academic assistant..."),
    Message(role="user", content="""What is MTL?
    
---
**Evidence from library:**

[1] Paper A (2023)
Multi-task learning is...

[2] Paper B (2024)
In NLP, MTL involves...""")
]
```

**Turn 2 (BROKEN - re-injects instructions)**:
```python
messages = [
    Message(role="system", content="You are an academic assistant..."),
    Message(role="user", content="What is MTL?" + evidence),
    Message(role="assistant", content="MTL is a paradigm..."),
    Message(role="user", content="""Is there overlap?
    
---
**Instructions:**        ← Problem!
Answer using the evidence above...
Cite every claim...
Follow these requirements...""")  # LLM thinks these are NEW instructions!
]
```

**Turn 2 (FIXED - natural continuation)**:
```python
messages = [
    Message(role="system", content="You are an academic assistant..."),
    Message(role="user", content="What is MTL?" + evidence),
    Message(role="assistant", content="MTL is a paradigm..."),
    Message(role="user", content="Is there overlap?")  # ← Just the question!
]
```

## Key Code Snippets

### 1. Query Condensation Prompt

```python
CONDENSE_PROMPT = """Convert a follow-up question into a standalone question.

## Rules
- **Output ONLY the standalone question** - no explanations
- Replace pronouns with specific nouns
- Include implicit context from history
- Maintain original intent

## Example
History: User: What is BERT?
Follow-up: How does it work?
Standalone: How does BERT work?

---

[Now process the actual conversation...]
"""
```

**Critical**: "Output ONLY" prevents meta-responses

### 2. Condensation Detection

```python
def should_condense(query: str, history: List[Message]) -> bool:
    if len([m for m in history if m.role == "user"]) == 0:
        return False  # First turn
    
    q = query.lower()
    
    # Pronouns: "it", "they", "that"...
    has_anaphora = any(
        f" {word} " in f" {q} " 
        for word in ["it", "they", "that", "these"]
    )
    
    # Ellipsis: "what about", "how about"...
    has_ellipsis = any(phrase in q for phrase in ["what about", "how about"])
    
    # Comparison: "overlap", "versus"...
    has_comparison = any(phrase in q for phrase in ["overlap", "versus"])
    
    # Short queries likely follow-ups
    is_short = len(q.split()) < 8
    
    return has_anaphora or has_ellipsis or (has_comparison and is_short)
```

### 3. Message Construction

```python
def chat(self, query, session_id):
    # ... retrieval code ...
    
    if session_id:
        history = self.conversation_store.get_messages(session_id)
        is_new_session = len([m for m in history if m.role == "user"]) == 0
        
        if is_new_session:
            # First turn: embed evidence in user message
            user_message = self._build_first_turn_message(query, snippets)
        else:
            # Follow-up: ONLY the question
            user_message = query
        
        self.conversation_store.append_message(session_id, "user", user_message)
        messages = self.conversation_store.get_messages(session_id)
    
    # Generate answer...
```

### 4. First Turn Message Builder

```python
def _build_first_turn_message(self, question: str, snippets: list) -> str:
    # Build compact context
    context_blocks = []
    for s in snippets:
        cid = s.get("citation_id")
        title = s.get("title")
        text = s.get("snippet")
        context_blocks.append(f"[{cid}] {title}\n{text}")
    
    context = "\n\n".join(context_blocks)
    
    return f"""{question}

---
**Evidence from library:**

{context}"""
```

## Debugging Checklist

When follow-ups fail, check:

1.  **Is query being condensed?**
   ```
   Look for: " Detected follow-up question, condensing..."
   ```

2.  **Is standalone query reasonable?**
   ```
   Look for: " Query condensation: Original: ... Standalone: ..."
   ```

3.  **Is retrieval using condensed query?**
   ```
   Verify: retrieval_query = condense_query(...) used in query_hybrid_rrf()
   ```

4.  **Is follow-up message plain?**
   ```
   Look for: " Follow-up turn (#N): plain question only"
   Not: Message with embedded instructions
   ```

5.  **Is system prompt only sent once?**
   ```
   Verify: First message in history has role="system"
   No other system messages in history
   ```

## Common Mistakes & Fixes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Using raw query for retrieval | Wrong documents retrieved | Use `retrieval_query = condense_query(query, history)` |
| Embedding instructions in follow-ups | "I'm ready to begin" | Use `user_message = query` for turn > 1 |
| Re-injecting system prompt | Repetitive responses | Send system prompt only at session creation |
| High condensation temperature | Hallucinated queries | Use `temperature=0.2` for extraction |
| No context trimming | Token limit errors | Trim messages to `max_chars=8000` |

## Quick Test

```python
# Test query condensation:
from backend.query_condenser import QueryCondenser
from backend.model_providers import Message, ProviderManager

provider = ProviderManager(active_provider_id="ollama")
condenser = QueryCondenser(provider)

history = [
    Message(role="user", content="What is BERT?"),
    Message(role="assistant", content="BERT is a transformer model...")
]

query = "How does it compare to GPT?"
standalone = condenser.condense_query(query, history)
print(f"Original: {query}")
print(f"Standalone: {standalone}")
# Expected: "How does BERT compare to GPT?"
```

## Files to Review

1. **`backend/query_condenser.py`**: Query condensation logic
2. **`backend/interface.py`**: Main chat method (lines ~620-750)
3. **`backend/conversation_store.py`**: Message history management
4. **`backend/academic_prompts.py`**: System prompt and instructions

---

**Remember**: The key insight is that follow-up questions need:
1. **Condensation before retrieval** (for correct documents)
2. **Plain message structure** (for natural conversation)
3. **Stable system prompt** (no re-injection)
