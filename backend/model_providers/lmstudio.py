"""
LM Studio provider for local LLM inference.

LM Studio (https://lmstudio.ai/) provides a local server that's compatible
with OpenAI's API format, making it easy to run models locally without
sending data to external services.
"""

from typing import Dict, Any, List, Optional
from .base import (
    structured_request,
    repetition_penalty,
    BaseProvider, Message, ChatResponse, ModelInfo,
    ProviderError, ProviderAuthenticationError, ProviderConnectionError,
    ProviderRateLimitError, ProviderContextError,
    MessageAdapter, ParameterMapper
)


class LMStudioProvider(BaseProvider):
    """Provider implementation for LM Studio local server."""
    
    def __init__(self):
        super().__init__(
            id="lmstudio",
            label="LM Studio (Local)",
            default_model="",  # User must load a model in LM Studio first
            supports_streaming=True,
            requires_api_key=False,  # Local service, no API key needed
        )
        self._client = None
    
    def _get_client(self, credentials: Dict[str, Any]):
        """Get or create OpenAI-compatible client for LM Studio."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ProviderError(
                "OpenAI package not installed. Install with: pip install openai"
            )
        
        # LM Studio default port is 1234
        base_url = credentials.get("base_url", "http://localhost:1234/v1")
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        
        # LM Studio doesn't require an API key, but the OpenAI client expects one
        # We pass a dummy key to satisfy the client initialization
        return OpenAI(api_key="lm-studio", base_url=base_url)
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate LM Studio connection by checking if server is running."""
        try:
            client = self._get_client(credentials)
            # Try to list models as a validation check
            models = client.models.list()
            if not models.data:
                raise ProviderError(
                    "LM Studio is running but no models are loaded. "
                    "Please load a model in LM Studio before using it."
                )
            return True
        except ImportError as e:
            raise ProviderError(str(e))
        except Exception as e:
            error_msg = str(e).lower()
            if "connection" in error_msg or "refused" in error_msg or "failed to connect" in error_msg:
                raise ProviderConnectionError(
                    "Cannot connect to LM Studio. Make sure LM Studio is running "
                    "and the local server is started on the configured port."
                )
            else:
                raise ProviderError(f"LM Studio validation failed: {str(e)}")
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """
        List available models from LM Studio.
        
        Returns models that are currently loaded in LM Studio.
        """
        try:
            client = self._get_client(credentials)
            models_response = client.models.list()
            
            if not models_response.data:
                return []
            
            # Convert to our ModelInfo format
            available_models = []
            for model in models_response.data:
                # LM Studio returns basic model info
                model_info = ModelInfo(
                    id=model.id,
                    name=model.id,
                    description="Local model via LM Studio",
                    context_length=None  # LM Studio doesn't expose this in API
                )
                available_models.append(model_info)
            
            return available_models
                
        except Exception as e:
            raise ProviderError(f"Failed to list LM Studio models: {str(e)}")
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """Generate a chat completion using LM Studio."""
        try:
            client = self._get_client(credentials)
            
            # Use MessageAdapter for OpenAI-compatible format
            openai_messages = MessageAdapter.to_openai(messages)
            
            # Map standard parameters
            mapped_params = ParameterMapper.map_params(kwargs, self.id)
            
            # Make the API call
            # LM Studio supports standard OpenAI parameters
            response = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=mapped_params.get("top_p", 0.9),
                frequency_penalty=repetition_penalty(kwargs, mapped_params.get("frequency_penalty", 0.3)),
                presence_penalty=kwargs.get("presence_penalty", 0.0),
                **structured_request(kwargs),
            )
            
            # Extract response
            content = response.choices[0].message.content or ""
            
            # Parse usage if available
            usage = None
            if hasattr(response, 'usage') and response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            
            return ChatResponse(
                content=content,
                model=response.model if hasattr(response, 'model') else model,
                usage=usage,
                raw=response.model_dump() if hasattr(response, 'model_dump') else None
            )
            
        except Exception as e:
            error_msg = str(e).lower()
            if "connection" in error_msg or "refused" in error_msg:
                raise ProviderConnectionError(
                    f"Lost connection to LM Studio: {str(e)}"
                )
            elif "context length" in error_msg or "maximum context" in error_msg:
                raise ProviderContextError(
                    f"Context too long for model {model}: {str(e)}"
                )
            else:
                raise ProviderError(f"LM Studio chat failed: {str(e)}")
