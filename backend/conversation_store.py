"""
Conversation Store for managing stateful chat sessions.

Provides in-memory storage of conversation histories with support for:
- Multi-turn conversation tracking
- Context window management (truncation)
- Session lifecycle management
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from backend.model_providers import Message
from backend.academic_prompts import AcademicPrompts


@dataclass
class ConversationHistory:
    """Represents a chat session's conversation history."""
    session_id: str
    messages: List[Message]
    system_prompt: Optional[str] = None
    

class ConversationStore:
    """
    In-memory storage for conversation histories across chat sessions.
    
    Each session maintains its own message list with roles: system, user, assistant.
    Designed for easy migration to persistent storage (database/files) later.
    """
    
    def __init__(self):
        # Maps session_id -> ConversationHistory
        self._sessions: Dict[str, ConversationHistory] = {}
        
        # Default system prompt (can be overridden per session)
        self.default_system_prompt = AcademicPrompts.get_system_prompt()
    
    def get_messages(self, session_id: str, provider_id: Optional[str] = None) -> List[Message]:
        """
        Retrieve the message history for a session.
        
        Args:
            session_id: Unique session identifier
            provider_id: Optional provider ID for provider-specific prompt customization
            
        Returns:
            List of messages in chronological order, including system prompt
        """
        if session_id not in self._sessions:
            # Get provider-specific system prompt if available
            system_prompt = AcademicPrompts.get_system_prompt(provider_id)
            
            # Initialize new session with system prompt
            self._sessions[session_id] = ConversationHistory(
                session_id=session_id,
                messages=[Message(role="system", content=system_prompt)],
                system_prompt=system_prompt
            )
        
        return self._sessions[session_id].messages.copy()
    
    def append_message(self, session_id: str, role: str, content: str) -> None:
        """
        Add a new message to the session history.
        
        Args:
            session_id: Unique session identifier
            role: Message role ("user" or "assistant")
            content: Message content
        """
        # Ensure session exists
        if session_id not in self._sessions:
            self.get_messages(session_id)  # Initialize with system prompt
        
        message = Message(role=role, content=content)
        self._sessions[session_id].messages.append(message)
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear all messages from a session.
        
        Args:
            session_id: Unique session identifier
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists and has messages."""
        return session_id in self._sessions and len(self._sessions[session_id].messages) > 0
    
    def get_session_count(self) -> int:
        """Get the total number of active sessions."""
        return len(self._sessions)
    
    def trim_messages_for_context(
        self, 
        messages: List[Message], 
        max_messages: int = 20,
        max_chars: int = 8000
    ) -> List[Message]:
        """
        Trim conversation history to fit within context window constraints.
        
        Strategy:
        1. Always keep the system message (first message)
        2. Keep the most recent N messages within character limit
        3. Prefer keeping complete user-assistant pairs
        
        Args:
            messages: Full message history
            max_messages: Maximum number of messages to keep (excluding system)
            max_chars: Maximum total characters (approximate token limit)
            
        Returns:
            Trimmed message list that fits constraints
        """
        if not messages:
            return []
        
        # Separate system message from conversation
        system_message = None
        conversation_messages = messages
        
        if messages[0].role == "system":
            system_message = messages[0]
            conversation_messages = messages[1:]
        
        # If already within limits, return as-is
        total_chars = sum(len(m.content) for m in messages)
        print(f"[ConversationStore] trim_messages: input={len(messages)} msgs, {total_chars} chars")
        print(f"[ConversationStore] limits: max_messages={max_messages}, max_chars={max_chars}")
        if len(conversation_messages) <= max_messages and total_chars <= max_chars:
            print(f"[ConversationStore] Within limits, returning all {len(messages)} messages")
            return messages
        
        # STRATEGY: Pinned anchor + sliding tail
        #
        # The first user+assistant exchange (the "anchor") contains the bulk of
        # the library evidence injected on turn 1.  The old reverse-only
        # algorithm would silently evict this evidence in long sessions,
        # causing the model to drift.  We now:
        #   1. Always pin the anchor (first user + first assistant message).
        #   2. Fill the remaining budget from the tail (most-recent messages),
        #      working backwards through the non-anchor messages.
        #   3. Middle messages that don't fit are dropped with a log line.
        #
        # Safety check: if the anchor doesn't conform to expected shape
        # (e.g. turn 1 errored and no assistant response was stored), fall
        # back to tail-only so we don't pin garbage.
        
        if (len(conversation_messages) >= 2
                and conversation_messages[0].role == "user"
                and conversation_messages[1].role == "assistant"):
            anchor_messages = conversation_messages[:2]
            tail_candidates = conversation_messages[2:]
        else:
            # Malformed history — fall back to tail-only strategy
            anchor_messages = []
            tail_candidates = conversation_messages

        anchor_chars = sum(len(m.content) for m in anchor_messages)
        char_count = (len(system_message.content) if system_message else 0) + anchor_chars
        
        # Fill remaining budget from the tail (most recent first)
        tail_kept = []
        max_tail_messages = max_messages - len(anchor_messages)
        for msg in reversed(tail_candidates):
            msg_chars = len(msg.content)
            if len(tail_kept) < max_tail_messages and char_count + msg_chars <= max_chars:
                tail_kept.insert(0, msg)
                char_count += msg_chars
            else:
                print(f"[ConversationStore] Dropped middle message to preserve anchor + recency")
                # Do NOT break — continue scanning so the loop finishes cleanly
                # (We must not use 'break' here: there may be smaller messages
                # further back that could still fit, but sliding-tail correctness
                # requires we stop at the first message that doesn't fit to keep
                # the tail contiguous.  Use break intentionally.)
                break

        # Reconstruct: system → anchor → tail
        kept_messages = anchor_messages + tail_kept
        result = []
        if system_message:
            result.append(system_message)
        result.extend(kept_messages)
        
        print(f"[ConversationStore] Trimmed: anchor={len(anchor_messages)}, "
              f"tail={len(tail_kept)}, total={len(result)} msgs, {char_count} chars")
        
        return result
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        Get metadata about a session.
        
        Returns:
            Dictionary with session stats or None if session doesn't exist
        """
        if session_id not in self._sessions:
            return None
        
        history = self._sessions[session_id]
        messages = history.messages
        
        user_msgs = [m for m in messages if m.role == "user"]
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        total_chars = sum(len(m.content) for m in messages)
        
        return {
            "session_id": session_id,
            "total_messages": len(messages),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "total_characters": total_chars,
            "has_system_prompt": any(m.role == "system" for m in messages)
        }
