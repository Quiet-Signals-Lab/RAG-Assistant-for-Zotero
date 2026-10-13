"""
Provider consistency tests for RAG Assistant for Zotero.

Tests that all providers handle the same queries consistently and pass validation.
"""

import pytest
from backend.model_providers.base import (
    Message, 
    ChatResponse,
    ResponseValidator,
    MessageAdapter,
    ParameterMapper
)


class TestMessageAdapter:
    """Test MessageAdapter formats messages correctly for each provider."""
    
    def test_to_openai(self):
        """Test OpenAI format conversion."""
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!")
        ]
        
        result = MessageAdapter.to_openai(messages)
        
        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful."
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"
    
    def test_to_anthropic(self):
        """Test Anthropic format separates system message."""
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!")
        ]
        
        system, conversation = MessageAdapter.to_anthropic(messages)
        
        assert system == "You are helpful."
        assert len(conversation) == 2
        assert conversation[0]["role"] == "user"
        assert conversation[1]["role"] == "assistant"
    
    def test_to_gemini(self):
        """Test Gemini format uses 'model' role and system_instruction."""
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!")
        ]
        
        system_inst, history = MessageAdapter.to_gemini(messages)
        
        assert system_inst == "You are helpful."
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "model"  # Not 'assistant'
        assert "parts" in history[0]


class TestParameterMapper:
    """Test ParameterMapper translates parameters correctly."""
    
    def test_ollama_params(self):
        """Test Ollama parameter mapping."""
        params = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 50,
            "repetition_penalty": 1.1
        }
        
        mapped = ParameterMapper.map_params(params, "ollama")
        
        assert "temperature" in mapped
        assert "top_p" in mapped
        assert "top_k" in mapped
        assert "repeat_penalty" in mapped  # Maps from repetition_penalty to repeat_penalty
        assert mapped["repeat_penalty"] == 1.1
    
    def test_openai_params(self):
        """Test OpenAI parameter mapping."""
        params = {
            "temperature": 0.7,
            "top_p": 0.9,
            "repetition_penalty": 1.1
        }
        
        mapped = ParameterMapper.map_params(params, "openai")
        
        assert "temperature" in mapped
        assert "top_p" in mapped
        assert "frequency_penalty" in mapped  # Mapped from repetition_penalty
        assert "top_k" not in mapped  # OpenAI doesn't support top_k
    
    def test_anthropic_params(self):
        """Test Anthropic parameter mapping."""
        params = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 50,
            "repetition_penalty": 1.1
        }
        
        mapped = ParameterMapper.map_params(params, "anthropic")
        
        assert "temperature" in mapped
        assert "top_p" in mapped
        assert "top_k" in mapped
        assert "repetition_penalty" not in mapped  # Not supported
    
    def test_unmapped_params_preserved(self):
        """Test that unmapped parameters are preserved."""
        params = {
            "temperature": 0.7,
            "custom_param": "value"
        }
        
        mapped = ParameterMapper.map_params(params, "openai")
        
        assert "temperature" in mapped
        assert "custom_param" in mapped  # Should be preserved


class TestResponseValidator:
    """Test ResponseValidator detects common failure patterns."""
    
    def test_valid_response(self):
        """Test that valid responses pass validation."""
        response = ChatResponse(
            content="Here is a comprehensive answer based on the sources provided [1].",
            model="test-model",
            usage=None
        )
        
        is_valid, issues = ResponseValidator.validate_chat_response(response, "openai")
        
        assert is_valid
        assert len(issues) == 0
    
    def test_meta_response_detection(self):
        """Test detection of meta-responses."""
        response = ChatResponse(
            content="I'm ready to help you with your questions about the Zotero library.",
            model="test-model",
            usage=None
        )
        
        is_valid, issues = ResponseValidator.validate_chat_response(response, "openai")
        
        assert not is_valid
        assert any("Meta-response" in issue for issue in issues)
    
    def test_empty_response_detection(self):
        """Test detection of empty or very short responses."""
        response = ChatResponse(
            content="Yes.",
            model="test-model",
            usage=None
        )
        
        is_valid, issues = ResponseValidator.validate_chat_response(response, "openai")
        
        assert not is_valid
        assert any("too short" in issue.lower() for issue in issues)

    def test_error_message_detection(self):
        """Test detection of error messages in response content."""
        response = ChatResponse(
            content="Error: Failed to process your request due to insufficient context.",
            model="test-model",
            usage=None
        )
        
        is_valid, issues = ResponseValidator.validate_chat_response(response, "openai")
        
        assert not is_valid
        assert any("Error message" in issue for issue in issues)


# Integration test markers
@pytest.mark.integration
@pytest.mark.skipif(True, reason="Requires API credentials and running backend")
class TestProviderIntegration:
    """
    Integration tests for provider consistency.
    
    These tests require:
    - Valid API credentials for each provider
    - Running Ollama instance (for local tests)
    - Actual Zotero library with indexed documents
    
    Mark with @pytest.mark.integration to skip by default.
    Run with: pytest -m integration backend/tests/test_providers.py -v
    """
    
    FIXED_QUERY = "Summarize distribution shifts from my Zotero library"
    PROVIDERS = ["ollama", "openai", "anthropic", "google", "mistral", "groq", "openrouter"]
    
    @pytest.mark.parametrize("provider_id", PROVIDERS)
    def test_provider_consistency(self, provider_id):
        """Test that each provider returns valid, consistent responses."""
        pytest.skip("Integration test - requires setup")
        # Implementation would go here when integration testing is set up
        # from backend.interface import ZoteroChatbot
        # chatbot = ZoteroChatbot(...)
        # result = chatbot.chat(self.FIXED_QUERY)
        # assert result["summary"]
        # response = ChatResponse(content=result["summary"], model=provider_id, usage=None)
        # is_valid, _ = ResponseValidator.validate_chat_response(response, provider_id)
        # assert is_valid, f"{provider_id} failed validation"


if __name__ == "__main__":
    # Run basic tests
    pytest.main([__file__, "-v", "-m", "not integration"])


def test_no_chosen_model_uses_the_first_installed_on_a_local_server():
    """Ollama's nominal default is not what a user pulled; the first installed model is."""
    from unittest.mock import Mock
    from backend.model_providers import ProviderManager
    manager = ProviderManager(active_provider_id="ollama", active_model=None, credentials={})
    provider = Mock(id="ollama", requires_api_key=False, default_model="llama3.2")
    provider.list_models.return_value = [Mock(id="gemma3:4b"), Mock(id="llama3.2:3b")]
    manager.get_active_provider = lambda: provider
    assert manager.get_active_model() == "gemma3:4b"
    assert manager.get_active_model() == "gemma3:4b" and provider.list_models.call_count == 1, "listing is cached"
    manager.__dict__.pop("_installed_cache")
    provider.list_models.return_value = []
    assert manager.get_active_model() == "", "a server with nothing installed means no model"
    manager.__dict__.pop("_installed_cache")
    provider.list_models.side_effect = ConnectionError("down")
    assert manager.get_active_model() == "llama3.2", "a server that cannot be asked keeps the nominal default"
    manager.active_model = "qwen3:4b"
    assert manager.get_active_model() == "qwen3:4b"


def test_chat_sends_the_resolved_model_not_the_nominal_default():
    from unittest.mock import Mock
    from backend.model_providers import ProviderManager, Message
    import backend.model_providers as mp
    manager = ProviderManager(active_provider_id="ollama", active_model=None, credentials={})
    provider = Mock(id="ollama", label="Ollama (Local)", requires_api_key=False, default_model="llama3.2")
    provider.list_models.return_value = [Mock(id="gemma3:4b")]
    manager.get_active_provider = lambda: provider
    original = mp.get_provider
    mp.get_provider = lambda pid: provider
    try:
        manager.chat(messages=[Message(role="user", content="hi")])
        assert provider.chat.call_args.kwargs["model"] == "gemma3:4b"
    finally:
        mp.get_provider = original
