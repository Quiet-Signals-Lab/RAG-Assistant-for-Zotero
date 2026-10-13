"""
Model provider registry and factory.

Provides a central registry for all available LLM providers and utilities
for managing provider instances, credentials, and model selection.
"""

from typing import Dict, Optional, List
from .base import ModelProvider, Message, ChatResponse, ModelInfo, ProviderError
from .ollama import OllamaProvider
from .lmstudio import LMStudioProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .github_models import GitHubModelsProvider
from .additional import (
    MistralProvider,
    GoogleProvider,
    GroqProvider,
    OpenRouterProvider,
)


# Global provider registry
_PROVIDERS: Dict[str, ModelProvider] = {}


def register_provider(provider: ModelProvider) -> None:
    """Register a provider in the global registry."""
    _PROVIDERS[provider.id] = provider


def get_provider(provider_id: str) -> Optional[ModelProvider]:
    """Get a provider by ID from the registry."""
    return _PROVIDERS.get(provider_id)


def list_providers() -> List[ModelProvider]:
    """Get all registered providers."""
    return list(_PROVIDERS.values())


def get_provider_info() -> List[Dict]:
    """Get metadata about all providers for UI/API consumption."""
    return [
        {
            "id": p.id,
            "label": p.label,
            "default_model": p.default_model,
            "supports_streaming": p.supports_streaming,
            "requires_api_key": p.requires_api_key,
        }
        for p in _PROVIDERS.values()
    ]


# Initialize all providers on module load
def _initialize_providers():
    """Register all available providers."""
    providers = [
        OllamaProvider(),
        LMStudioProvider(),
        OpenAIProvider(),
        AnthropicProvider(),
        GitHubModelsProvider(),
        MistralProvider(),
        GoogleProvider(),
        GroqProvider(),
        OpenRouterProvider(),
    ]
    
    for provider in providers:
        register_provider(provider)


# Auto-initialize on import
_initialize_providers()


class ProviderManager:
    """
    High-level manager for working with providers.
    
    Handles provider selection, credential management, and provides
    a simplified interface for chat operations.
    """
    
    def __init__(
        self,
        active_provider_id: str = "ollama",
        active_model: str = None,
        credentials: Optional[Dict[str, Dict]] = None,
    ):
        """
        Initialize provider manager.
        
        Args:
            active_provider_id: ID of the default provider to use
            active_model: Model ID to use (None = use provider's default)
            credentials: Dict mapping provider_id -> credentials dict
        """
        self.active_provider_id = active_provider_id
        self.active_model = active_model
        self.credentials = credentials or {}
    
    def get_active_provider(self) -> ModelProvider:
        """Get the currently active provider."""
        provider = get_provider(self.active_provider_id)
        if not provider:
            raise ProviderError(
                f"Provider '{self.active_provider_id}' not found. "
                f"Available: {', '.join(_PROVIDERS.keys())}"
            )
        return provider
    
    def get_active_model(self) -> str:
        """The chosen model; else, for a local server, the first model it has installed;
        else the provider's nominal default.

        Ollama's nominal default "llama3.2" is not installed on a machine that pulled
        "llama3.2:3b", and every job sent to it failed while the desk reported a model.
        A local server that is up but has nothing installed yields "" (no model).
        """
        if self.active_model:
            return self.active_model
        provider = self.get_active_provider()
        if not provider.requires_api_key:
            installed = self._installed_models(provider)
            if installed is not None:
                return installed[0] if installed else ""
        return provider.default_model

    _INSTALLED_TTL = 60.0  # seconds; get_active_model is called on every job

    def _installed_models(self, provider) -> Optional[List[str]]:
        """Model ids a local server reports, cached briefly; None when it cannot be asked."""
        import time
        cache = self.__dict__.setdefault("_installed_cache", {})
        hit = cache.get(provider.id)
        if hit and time.monotonic() - hit[0] < self._INSTALLED_TTL:
            return hit[1]
        try:
            names = [m.id for m in provider.list_models(self.get_credentials(provider.id))]
        except Exception:
            return None
        cache[provider.id] = (time.monotonic(), names)
        return names
    
    def get_credentials(self, provider_id: Optional[str] = None) -> Dict:
        """Get credentials for a provider (active by default)."""
        pid = provider_id or self.active_provider_id
        return self.credentials.get(pid, {})
    
    def set_active_provider(self, provider_id: str, model: Optional[str] = None):
        """Switch the active provider and optionally model."""
        if provider_id not in _PROVIDERS:
            raise ProviderError(f"Unknown provider: {provider_id}")
        self.active_provider_id = provider_id
        self.active_model = model
    
    def set_credentials(self, provider_id: str, credentials: Dict):
        """Set credentials for a specific provider."""
        self.credentials[provider_id] = credentials
    
    def validate_provider(self, provider_id: Optional[str] = None) -> bool:
        """Validate that a provider is configured and accessible."""
        pid = provider_id or self.active_provider_id
        provider = get_provider(pid)
        if not provider:
            raise ProviderError(f"Provider '{pid}' not found")
        
        creds = self.get_credentials(pid)
        return provider.validate_credentials(creds)
    
    def list_models(self, provider_id: Optional[str] = None) -> List[ModelInfo]:
        """List available models for a provider."""
        pid = provider_id or self.active_provider_id
        provider = get_provider(pid)
        if not provider:
            raise ProviderError(f"Provider '{pid}' not found")
        
        creds = self.get_credentials(pid)
        return provider.list_models(creds)
    
    def chat(
        self,
        messages: List[Message],
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """
        Generate a chat completion using the specified (or active) provider.
        
        Args:
            messages: List of conversation messages
            provider_id: Provider to use (None = use active)
            model: Model to use (None = use active/default)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            **kwargs: Additional provider-specific parameters
            
        Returns:
            ChatResponse with generated content
        """
        pid = provider_id or self.active_provider_id
        provider = get_provider(pid)
        if not provider:
            raise ProviderError(f"Provider '{pid}' not found")
        
        model_id = model or (self.get_active_model() if pid == self.active_provider_id else provider.default_model)
        if not model_id:
            raise ProviderError(f"No model is installed on {provider.label}")
        
        creds = self.get_credentials(pid)
        
        return provider.chat(
            credentials=creds,
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


# Convenience function for simple use cases
def generate_chat_response(
    prompt: str,
    provider_id: str = "ollama",
    model: Optional[str] = None,
    credentials: Optional[Dict] = None,
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str:
    """
    Simple wrapper to generate a chat response from a single prompt.
    
    Args:
        prompt: User prompt/question
        provider_id: Provider to use
        model: Model to use (None = provider default)
        credentials: Provider credentials
        temperature: Sampling temperature
        max_tokens: Max tokens to generate
        
    Returns:
        Generated text response
    """
    provider = get_provider(provider_id)
    if not provider:
        raise ProviderError(f"Provider '{provider_id}' not found")
    
    messages = [Message(role="user", content=prompt)]
    model_id = model or provider.default_model
    creds = credentials or {}
    
    response = provider.chat(
        credentials=creds,
        model=model_id,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    
    return response.content


# Export main components
__all__ = [
    "ModelProvider",
    "Message",
    "ChatResponse",
    "ModelInfo",
    "ProviderError",
    "ProviderManager",
    "register_provider",
    "get_provider",
    "list_providers",
    "get_provider_info",
    "generate_chat_response",
]
