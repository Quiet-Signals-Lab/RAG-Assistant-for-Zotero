"""
Base interface for LLM providers.

Defines the ModelProvider protocol that all concrete providers must implement.
This ensures a consistent interface regardless of whether using local models (Ollama)
or cloud APIs (OpenAI, Anthropic, etc.).
"""

from typing import Protocol, Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class Message:
    """Standard message format for chat interactions."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class ChatResponse:
    """Normalized response from any LLM provider."""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None  # {"prompt_tokens": X, "completion_tokens": Y}
    raw: Optional[Dict[str, Any]] = None  # Raw response for debugging


@dataclass
class ModelInfo:
    """Information about an available model."""
    id: str
    name: str
    description: Optional[str] = None
    context_length: Optional[int] = None


class ProviderError(Exception):
    """Base exception for provider-related errors."""
    pass


class ProviderConnectionError(ProviderError):
    """Raised when unable to connect to provider."""
    pass


class ProviderAuthenticationError(ProviderError):
    """Raised when authentication fails."""
    pass


class ProviderRateLimitError(ProviderError):
    """Raised when rate limit is exceeded."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderContextError(ProviderError):
    """Raised when context length is exceeded."""
    def __init__(self, message: str, max_length: Optional[int] = None):
        super().__init__(message)
        self.max_length = max_length


class MessageAdapter:
    """Adapts standard Message format to provider-specific formats."""
    
    @staticmethod
    def to_openai(messages: List[Message]) -> List[Dict[str, str]]:
        """Convert to OpenAI format (also used by Ollama, Mistral, Groq, OpenRouter)."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]
    
    @staticmethod
    def to_anthropic(messages: List[Message]) -> tuple[Optional[str], List[Dict[str, str]]]:
        """
        Convert to Anthropic format.
        Returns (system_message, conversation_messages).
        System message must be separate parameter.
        """
        system_message = None
        conversation_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                conversation_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        return system_message, conversation_messages
    
    @staticmethod
    def to_gemini(messages: List[Message]) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """
        Convert to Google Gemini format.
        Returns (system_instruction, history).
        System instruction is model parameter, history uses 'model' role instead of 'assistant'.
        """
        system_instruction = None
        history = []
        
        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                # Gemini uses 'model' role instead of 'assistant'
                role = "user" if msg.role == "user" else "model"
                history.append({
                    "role": role,
                    "parts": [msg.content]
                })
        
        return system_instruction, history


class ParameterMapper:
    """Maps standard parameter names to provider-specific equivalents."""
    
    # Mapping of standard param names to provider-specific names
    MAPPINGS = {
        "ollama": {
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
            "repetition_penalty": "repeat_penalty",
        },
        "openai": {
            "temperature": "temperature",
            "top_p": "top_p",
            "repetition_penalty": "frequency_penalty",
        },
        "anthropic": {
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
        },
        "google": {
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
        },
        "mistral": {
            "temperature": "temperature",
            "top_p": "top_p",
        },
        "groq": {
            "temperature": "temperature",
            "top_p": "top_p",
            "repetition_penalty": "frequency_penalty",
        },
        "openrouter": {
            "temperature": "temperature",
            "top_p": "top_p",
            "repetition_penalty": "frequency_penalty",
        },
    }
    
    @staticmethod
    def map_params(params: Dict[str, Any], provider_id: str) -> Dict[str, Any]:
        """
        Map standard parameter names to provider-specific names.
        Only includes parameters supported by the provider.
        """
        mapping = ParameterMapper.MAPPINGS.get(provider_id, {})
        mapped = {}
        
        for key, value in params.items():
            # Map the key to provider-specific name
            provider_key = mapping.get(key)
            if provider_key:
                mapped[provider_key] = value
            # Keep unmapped keys if they're not in our standard set
            elif key not in ["top_p", "top_k", "repetition_penalty"]:
                mapped[key] = value
        
        return mapped


class ResponseValidator:
    """Validates provider responses to detect common failure patterns."""
    
    # Phrases indicating meta-responses instead of actual answers
    META_RESPONSE_PHRASES = [
        "i'm ready",
        "i understand",
        "okay, i'll",
        "i will now",
        "let me know",
        "i'd be happy to",
        "i can help",
    ]
    
    @staticmethod
    def validate_chat_response(response: ChatResponse, provider_id: str) -> tuple[bool, List[str]]:
        """
        Validate a chat response for common issues.
        Returns (is_valid, list_of_issues).
        """
        issues = []
        content_lower = response.content.lower().strip()
        
        # Check for meta-responses
        if any(phrase in content_lower for phrase in ResponseValidator.META_RESPONSE_PHRASES):
            issues.append("Meta-response detected (acknowledgment instead of answer)")
        
        # Check for empty or very short responses
        if len(response.content.strip()) < 10:
            issues.append("Response too short or empty")
        
        # Check for error messages in response
        error_indicators = ["error:", "exception:", "failed to", "could not"]
        if any(indicator in content_lower for indicator in error_indicators):
            issues.append("Error message in response content")
        
        return len(issues) == 0, issues


# Size limits that strict schema modes may refuse (OpenAI documents a subset of JSON
# Schema for strict mode). The clerk's guards check every one of them anyway.
_UNENFORCED = {"maxLength", "minLength", "maxItems", "minItems"}


def strict_schema(schema: Any) -> Any:
    """The schema without size limits, for servers that enforce it strictly."""
    if isinstance(schema, dict):
        return {k: strict_schema(v) for k, v in schema.items() if k not in _UNENFORCED}
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


def structured_request(kwargs: Dict[str, Any], mode: str = "json_schema") -> Dict[str, Any]:
    """Extra arguments for an OpenAI-style create() when the caller wants JSON.

    `kwargs["response_schema"]` is a JSON schema from the desk clerk. "json_schema"
    asks the server to constrain decoding to it; "json_object" only asks for valid
    JSON, for APIs that accept no schema. A per-request timeout is passed through so
    an abandoned call closes its connection and a local server stops generating.
    """
    extra: Dict[str, Any] = {}
    if kwargs.get("timeout"):
        extra["timeout"] = kwargs["timeout"]
    schema = kwargs.get("response_schema")
    if schema:
        if mode == "json_schema":
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "desk_job", "schema": strict_schema(schema), "strict": True},
            }
        else:
            extra["response_format"] = {"type": "json_object"}
    return extra


def repetition_penalty(kwargs: Dict[str, Any], default: float) -> float:
    """No repetition penalty for JSON: it penalises the quotes, commas and braces JSON must repeat."""
    return 0.0 if kwargs.get("response_schema") else default


class ModelProvider(Protocol):
    """
    Protocol defining the interface all LLM providers must implement.
    
    Providers should implement this interface to work with the chatbot system.
    Each provider handles its own API authentication, request formatting,
    and response normalization.
    """
    
    @property
    def id(self) -> str:
        """Unique identifier for this provider (e.g., 'ollama', 'openai')."""
        ...
    
    @property
    def label(self) -> str:
        """Human-readable label for UI display (e.g., 'Ollama (Local)', 'OpenAI')."""
        ...
    
    @property
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming responses."""
        ...
    
    @property
    def default_model(self) -> str:
        """Default model ID for this provider."""
        ...
    
    @property
    def requires_api_key(self) -> bool:
        """Whether this provider requires an API key."""
        ...
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """
        Validate that the provided credentials are valid.
        
        Args:
            credentials: Dictionary containing provider-specific credentials
                        (e.g., {"api_key": "sk-..."})
        
        Returns:
            True if credentials are valid, False otherwise
            
        Raises:
            ProviderConnectionError: If unable to reach provider
            ProviderAuthenticationError: If credentials are invalid
        """
        ...
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """
        Get list of available models from this provider.
        
        Args:
            credentials: Provider-specific credentials
            
        Returns:
            List of available models with metadata
            
        Raises:
            ProviderError: If unable to retrieve models
        """
        ...
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """
        Generate a chat completion using this provider.
        
        Args:
            credentials: Provider-specific credentials
            model: Model ID to use for generation
            messages: List of messages in the conversation
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Normalized ChatResponse object
            
        Raises:
            ProviderError: If generation fails
        """
        ...


class BaseProvider:
    """
    Base class with common functionality for providers.
    
    Concrete providers can inherit from this to get standard implementations
    of common methods and utilities.
    """
    
    def __init__(
        self,
        id: str,
        label: str,
        default_model: str,
        supports_streaming: bool = False,
        requires_api_key: bool = True,
    ):
        self._id = id
        self._label = label
        self._default_model = default_model
        self._supports_streaming = supports_streaming
        self._requires_api_key = requires_api_key
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def label(self) -> str:
        return self._label
    
    @property
    def supports_streaming(self) -> bool:
        return self._supports_streaming
    
    @property
    def default_model(self) -> str:
        return self._default_model
    
    @property
    def requires_api_key(self) -> bool:
        return self._requires_api_key
    
    def _cached(self, key: tuple, make):
        """One SDK client per credentials: each one owns a connection pool, and a new
        one per call opened a fresh TLS connection for every clerk job."""
        clients = self.__dict__.setdefault("_clients", {})
        if key not in clients:
            clients[key] = make()
        return clients[key]

    def _check_credentials(self, credentials: Dict[str, Any], required_keys: List[str]):
        """Helper to validate required credential keys are present."""
        missing = [key for key in required_keys if not credentials.get(key)]
        if missing:
            raise ProviderAuthenticationError(
                f"Missing required credentials for {self.id}: {', '.join(missing)}"
            )
