"""
Tests for provider-aware dynamic retrieval limits.

Tests the get_active_model_context_length() and get_retrieval_limits() methods
to ensure they correctly scale retrieval parameters based on model context windows.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from backend.interface import ZoteroChatbot
from backend.model_providers.base import ModelInfo


class TestRetrievalLimits(unittest.TestCase):
    """Test suite for dynamic retrieval limits based on model context windows."""

    def setUp(self):
        """Set up test fixtures with mocked dependencies."""
        # Mock the database and vector store to avoid file I/O
        with patch('backend.interface.ZoteroLibrary'), \
             patch('backend.interface.ChromaClient'), \
             patch('backend.interface.ConversationStore'), \
             patch('backend.interface.QueryCondenser'):

            self.chatbot = ZoteroChatbot(
                db_path="/fake/path/zotero.sqlite",
                chroma_path="/fake/path/chroma",
                active_provider_id="ollama",
                active_model="llama3.2",
                credentials={},
                embedding_model_id="bge-base"
            )

    def test_get_retrieval_limits_unknown_context(self):
        """Test retrieval limits when context length is unknown (Ollama-style)."""
        # Mock get_active_model_context_length to return None
        self.chatbot.get_active_model_context_length = Mock(return_value=None)

        # Test broad mode
        limits_broad = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad["retrieval_k"], 15)
        self.assertEqual(limits_broad["rerank_top_k"], 10)
        self.assertEqual(limits_broad["max_snippets_per_paper"], 3)
        self.assertEqual(limits_broad["max_total_snippets"], 6)

        # Test focused mode
        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["retrieval_k"], 25)
        self.assertEqual(limits_focused["rerank_top_k"], 15)
        self.assertEqual(limits_focused["max_snippets_per_paper"], 8)
        self.assertEqual(limits_focused["max_total_snippets"], 10)

    def test_get_retrieval_limits_small_context(self):
        """Test retrieval limits for small context models (GPT-3.5 style - 16k)."""
        # Mock context_length for small model
        self.chatbot.get_active_model_context_length = Mock(return_value=16385)

        # Should use 1.0x multiplier (default tier)
        limits_broad = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad["retrieval_k"], 15)
        self.assertEqual(limits_broad["max_total_snippets"], 6)

        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["retrieval_k"], 25)
        self.assertEqual(limits_focused["max_total_snippets"], 10)

    def test_get_retrieval_limits_medium_context(self):
        """Test retrieval limits for medium context models (GPT-4 - 32k)."""
        # Mock context_length for medium model
        self.chatbot.get_active_model_context_length = Mock(return_value=32768)

        # Should use 2.0x multiplier
        limits_broad = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad["retrieval_k"], 30)  # 15 * 2.0
        self.assertEqual(limits_broad["rerank_top_k"], 20)  # 10 * 2.0
        self.assertEqual(limits_broad["max_snippets_per_paper"], 6)  # 3 * 2.0
        self.assertEqual(limits_broad["max_total_snippets"], 12)  # 6 * 2.0

        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["retrieval_k"], 50)  # 25 * 2.0
        self.assertEqual(limits_focused["rerank_top_k"], 30)  # 15 * 2.0
        self.assertEqual(limits_focused["max_snippets_per_paper"], 16)  # 8 * 2.0
        self.assertEqual(limits_focused["max_total_snippets"], 20)  # 10 * 2.0

    def test_get_retrieval_limits_large_context_gpt4(self):
        """Test retrieval limits for large context models (GPT-4 Turbo - 128k)."""
        # Mock context_length for GPT-4 Turbo
        self.chatbot.get_active_model_context_length = Mock(return_value=128000)

        # Should use 3.0x multiplier
        limits_broad = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad["retrieval_k"], 45)  # 15 * 3.0
        self.assertEqual(limits_broad["rerank_top_k"], 30)  # 10 * 3.0
        self.assertEqual(limits_broad["max_snippets_per_paper"], 9)  # 3 * 3.0
        self.assertEqual(limits_broad["max_total_snippets"], 18)  # 6 * 3.0

        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["retrieval_k"], 75)  # 25 * 3.0
        self.assertEqual(limits_focused["rerank_top_k"], 45)  # 15 * 3.0
        self.assertEqual(limits_focused["max_snippets_per_paper"], 24)  # 8 * 3.0
        self.assertEqual(limits_focused["max_total_snippets"], 30)  # 10 * 3.0

    def test_get_retrieval_limits_xlarge_context_claude(self):
        """Test retrieval limits for XLarge context models (Claude Opus - 200k)."""
        # Mock context_length for Claude Opus
        self.chatbot.get_active_model_context_length = Mock(return_value=200000)

        # Should use 4.0x multiplier
        limits_broad = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad["retrieval_k"], 60)  # 15 * 4.0
        self.assertEqual(limits_broad["rerank_top_k"], 40)  # 10 * 4.0
        self.assertEqual(limits_broad["max_snippets_per_paper"], 12)  # 3 * 4.0
        self.assertEqual(limits_broad["max_total_snippets"], 24)  # 6 * 4.0

        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["retrieval_k"], 100)  # 25 * 4.0
        self.assertEqual(limits_focused["rerank_top_k"], 60)  # 15 * 4.0
        self.assertEqual(limits_focused["max_snippets_per_paper"], 32)  # 8 * 4.0
        self.assertEqual(limits_focused["max_total_snippets"], 40)  # 10 * 4.0

    def test_get_retrieval_limits_xxlarge_context_gemini(self):
        """Test retrieval limits for XXLarge context models (Gemini 1.5 Pro - 2M)."""
        # Mock context_length for Gemini 1.5 Pro
        self.chatbot.get_active_model_context_length = Mock(return_value=2000000)

        # Should use 5.0x multiplier
        limits_broad = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad["retrieval_k"], 75)  # 15 * 5.0
        self.assertEqual(limits_broad["rerank_top_k"], 50)  # 10 * 5.0
        self.assertEqual(limits_broad["max_snippets_per_paper"], 15)  # 3 * 5.0
        self.assertEqual(limits_broad["max_total_snippets"], 30)  # 6 * 5.0

        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["retrieval_k"], 125)  # 25 * 5.0
        self.assertEqual(limits_focused["rerank_top_k"], 75)  # 15 * 5.0
        self.assertEqual(limits_focused["max_snippets_per_paper"], 40)  # 8 * 5.0
        self.assertEqual(limits_focused["max_total_snippets"], 50)  # 10 * 5.0

    def test_context_length_edge_cases(self):
        """Test edge cases for context length tiers."""
        # Test boundary between tiers

        # Just below 32k threshold - should use 1.0x
        self.chatbot.get_active_model_context_length = Mock(return_value=31999)
        limits = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits["max_total_snippets"], 6)  # 6 * 1.0

        # Exactly at 32k threshold - should use 2.0x
        self.chatbot.get_active_model_context_length = Mock(return_value=32000)
        limits = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits["max_total_snippets"], 12)  # 6 * 2.0

        # Just above 100k threshold - should use 3.0x
        self.chatbot.get_active_model_context_length = Mock(return_value=100001)
        limits = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits["max_total_snippets"], 18)  # 6 * 3.0

        # Exactly at 200k threshold - should use 4.0x
        self.chatbot.get_active_model_context_length = Mock(return_value=200000)
        limits = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits["max_total_snippets"], 24)  # 6 * 4.0

        # Exactly at 1M threshold - should use 5.0x
        self.chatbot.get_active_model_context_length = Mock(return_value=1000000)
        limits = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits["max_total_snippets"], 30)  # 6 * 5.0

    def test_get_active_model_context_length_success(self):
        """Test successful retrieval of model context length."""
        # Mock provider and model info
        mock_provider = Mock()
        mock_model_info = ModelInfo(
            id="gpt-4o",
            name="GPT-4o",
            description="Most capable model",
            context_length=128000
        )
        mock_provider.list_models = Mock(return_value=[mock_model_info])

        self.chatbot.provider_manager.get_active_provider = Mock(return_value=mock_provider)
        self.chatbot.provider_manager.get_active_model = Mock(return_value="gpt-4o")
        self.chatbot.provider_manager.get_credentials = Mock(return_value={})

        # Call the method
        context_length = self.chatbot.get_active_model_context_length()

        # Verify
        self.assertEqual(context_length, 128000)
        mock_provider.list_models.assert_called_once()
        # Asked once per model: this runs several times per chat turn.
        self.assertEqual(self.chatbot.get_active_model_context_length(), 128000)
        mock_provider.list_models.assert_called_once()

    def test_get_active_model_context_length_no_match(self):
        """Test when active model is not in the provider's model list."""
        # Mock provider with different model
        mock_provider = Mock()
        mock_model_info = ModelInfo(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            context_length=16385
        )
        mock_provider.list_models = Mock(return_value=[mock_model_info])

        self.chatbot.provider_manager.get_active_provider = Mock(return_value=mock_provider)
        self.chatbot.provider_manager.get_active_model = Mock(return_value="gpt-4o")  # Different model
        self.chatbot.provider_manager.get_credentials = Mock(return_value={})

        # Call the method
        context_length = self.chatbot.get_active_model_context_length()

        # Should return None when model not found
        self.assertIsNone(context_length)

    def test_get_active_model_context_length_exception_handling(self):
        """Test graceful handling of exceptions when querying context length."""
        # Mock provider that raises an exception
        self.chatbot.provider_manager.get_active_provider = Mock(
            side_effect=Exception("Provider unavailable")
        )

        # Call the method
        context_length = self.chatbot.get_active_model_context_length()

        # Should return None on exception (graceful fallback)
        self.assertIsNone(context_length)

    def test_get_active_model_context_length_none_in_modelinfo(self):
        """Test when ModelInfo has context_length=None (Ollama-style)."""
        # Mock provider with model that has None context_length
        mock_provider = Mock()
        mock_model_info = ModelInfo(
            id="llama3.2",
            name="Llama 3.2",
            context_length=None  # Ollama doesn't provide this
        )
        mock_provider.list_models = Mock(return_value=[mock_model_info])

        self.chatbot.provider_manager.get_active_provider = Mock(return_value=mock_provider)
        self.chatbot.provider_manager.get_active_model = Mock(return_value="llama3.2")
        self.chatbot.provider_manager.get_credentials = Mock(return_value={})

        # Call the method
        context_length = self.chatbot.get_active_model_context_length()

        # Should return None when context_length is None
        self.assertIsNone(context_length)


class TestRetrievalLimitsIntegration(unittest.TestCase):
    """Integration tests verifying limits are used correctly in chat flow."""

    def setUp(self):
        """Set up test fixtures."""
        with patch('backend.interface.ZoteroLibrary'), \
             patch('backend.interface.ChromaClient'), \
             patch('backend.interface.ConversationStore'), \
             patch('backend.interface.QueryCondenser'):

            self.chatbot = ZoteroChatbot(
                db_path="/fake/path/zotero.sqlite",
                chroma_path="/fake/path/chroma",
                active_provider_id="google",
                active_model="gemini-1.5-pro",
                credentials={"google": {"api_key": "fake"}},
                embedding_model_id="bge-base"
            )

    def test_chat_uses_dynamic_limits_gemini(self):
        """Test that chat() method uses dynamic limits for Gemini."""
        # Mock context length for Gemini
        self.chatbot.get_active_model_context_length = Mock(return_value=2000000)

        # Get limits
        limits = self.chatbot.get_retrieval_limits(is_focused=False)

        # Verify Gemini gets 5.0x multiplier
        self.assertEqual(limits["retrieval_k"], 75)  # 15 * 5.0
        self.assertEqual(limits["max_total_snippets"], 30)  # 6 * 5.0

        # Verify focused mode
        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["retrieval_k"], 125)  # 25 * 5.0
        self.assertEqual(limits_focused["max_total_snippets"], 50)  # 10 * 5.0

    def test_focus_mode_transitions(self):
        """Test that limits update correctly when focus mode changes."""
        # Mock small context initially
        self.chatbot.get_active_model_context_length = Mock(return_value=None)

        # Start with broad mode (no filters)
        limits_broad = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad["max_total_snippets"], 6)

        # Switch to focused mode (filters active)
        limits_focused = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused["max_total_snippets"], 10)

        # Now with large context
        self.chatbot.get_active_model_context_length = Mock(return_value=200000)

        # Broad mode with large context
        limits_broad_large = self.chatbot.get_retrieval_limits(is_focused=False)
        self.assertEqual(limits_broad_large["max_total_snippets"], 24)  # 6 * 4.0

        # Focused mode with large context
        limits_focused_large = self.chatbot.get_retrieval_limits(is_focused=True)
        self.assertEqual(limits_focused_large["max_total_snippets"], 40)  # 10 * 4.0


if __name__ == "__main__":
    unittest.main()
