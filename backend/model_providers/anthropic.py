"""
Anthropic provider for Claude models.

Implements the ModelProvider interface for Anthropic's API, supporting
Claude 4.x family of models (as of Feb 2026). Includes backward compatibility
mapping for deprecated Claude 3.x model identifiers.
"""

from typing import Dict, Any, List
from .base import (
    BaseProvider, Message, ChatResponse, ModelInfo,
    ProviderError, ProviderAuthenticationError, ProviderConnectionError,
    ProviderRateLimitError, ProviderContextError,
    MessageAdapter, ParameterMapper
)
import logging

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Provider implementation for Anthropic Claude models."""
    
    def __init__(self):
        super().__init__(
            id="anthropic",
            label="Anthropic",
            default_model="claude-opus-4-6",
            supports_streaming=True,
            requires_api_key=True,
        )
    
    def _get_client(self, credentials: Dict[str, Any]):
        """Get or create Anthropic client with credentials."""
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ProviderError(
                "Anthropic package not installed. Install with: pip install anthropic"
            )
        
        api_key = credentials.get("api_key")
        if not api_key:
            raise ProviderAuthenticationError("Anthropic API key is required")
        
        return Anthropic(api_key=api_key)
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate Anthropic API key by making a minimal test request.
        
        Uses Claude Haiku 4.5 (fastest current model) for validation.
        """
        try:
            client = self._get_client(credentials)
            # Use Claude 4.5 Haiku (fastest current model) for validation
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except ImportError as e:
            raise ProviderError(str(e))
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg or "401" in error_msg:
                raise ProviderAuthenticationError(f"Invalid Anthropic API key: {str(e)}")
            elif "connection" in error_msg or "network" in error_msg:
                raise ProviderConnectionError(f"Cannot connect to Anthropic: {str(e)}")
            else:
                raise ProviderError(f"Anthropic validation failed: {str(e)}")
    
    def validate_credentials_and_list_models(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate credentials AND return available models in one call.
        
        More efficient than separate validate + list_models calls.
        
        Returns:
            {
                "valid": bool,
                "models": List[ModelInfo],
                "message": str
            }
        """
        known_models = [
            ModelInfo(
                id="claude-opus-4-6",
                name="Claude Opus 4.6",
                description="Most intelligent; best for agents, coding, complex reasoning (200K context)",
                context_length=200000
            ),
            ModelInfo(
                id="claude-sonnet-4-5-20250929",
                name="Claude Sonnet 4.5",
                description="Speed + intelligence balance (200K context)",
                context_length=200000
            ),
            ModelInfo(
                id="claude-haiku-4-5-20251001",
                name="Claude Haiku 4.5",
                description="Fastest, near-frontier intelligence; ideal for high-volume RAG (200K context)",
                context_length=200000
            ),
        ]
        
        try:
            client = self._get_client(credentials)
            available_models = []
            validation_succeeded = False
            
            logger.info(f"[Anthropic Provider] Testing model availability...")
            
            # Test each model - this simultaneously validates credentials and discovers models
            for model_info in known_models:
                try:
                    client.messages.create(
                        model=model_info.id,
                        max_tokens=1,
                        messages=[{"role": "user", "content": "test"}]
                    )
                    # Success means both valid credentials AND accessible model
                    validation_succeeded = True
                    available_models.append(model_info)
                    logger.info(f"[Anthropic Provider] ✓ {model_info.id} accessible")
                except Exception as e:
                    error_str = str(e).lower()
                    # Check for authentication errors
                    if "authentication" in error_str or "api key" in error_str or "401" in error_str:
                        raise ProviderAuthenticationError(f"Invalid Anthropic API key: {str(e)}")
                    # If not a 404, assume model exists but rate limit/other issue
                    elif "not_found" not in error_str and "404" not in error_str:
                        validation_succeeded = True
                        available_models.append(model_info)
                        logger.info(f"[Anthropic Provider] ~ {model_info.id} included (non-404 error)")
                    else:
                        logger.info(f"[Anthropic Provider] ✗ {model_info.id} not available (404)")
            
            if validation_succeeded:
                return {
                    "valid": True,
                    "models": available_models if available_models else known_models,
                    "message": f"Found {len(available_models)} available models"
                }
            else:
                # All models returned 404 - might be a new API or all models deprecated
                return {
                    "valid": True,
                    "models": known_models,
                    "message": "Credentials valid but couldn't verify model availability"
                }
                
        except ProviderAuthenticationError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "connection" in error_msg or "network" in error_msg:
                raise ProviderConnectionError(f"Cannot connect to Anthropic: {str(e)}")
            else:
                raise ProviderError(f"Anthropic validation failed: {str(e)}")
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """
        List available Anthropic models by testing which ones are accessible.
        
        Anthropic doesn't provide a models.list() API, so we test known models
        to see which ones are accessible with the given API key.
        
        Note: This makes minimal API calls (1 token per model) to test availability.
        Results are based on testing 3 known Claude 4.x models.
        """
        # Known current models (as of Feb 2026)
        known_models = [
            ModelInfo(
                id="claude-opus-4-6",
                name="Claude Opus 4.6",
                description="Most intelligent; best for agents, coding, complex reasoning (200K context)",
                context_length=200000
            ),
            ModelInfo(
                id="claude-sonnet-4-5-20250929",
                name="Claude Sonnet 4.5",
                description="Speed + intelligence balance (200K context)",
                context_length=200000
            ),
            ModelInfo(
                id="claude-haiku-4-5-20251001",
                name="Claude Haiku 4.5",
                description="Fastest, near-frontier intelligence; ideal for high-volume RAG (200K context)",
                context_length=200000
            ),
        ]
        
        # Quick check: if no credentials, return known models
        if not credentials or not credentials.get("api_key"):
            return known_models
        
        try:
            client = self._get_client(credentials)
            available_models = []
            
            # Test each model with a minimal request (1 token output)
            for model_info in known_models:
                try:
                    client.messages.create(
                        model=model_info.id,
                        max_tokens=1,
                        messages=[{"role": "user", "content": "test"}]
                    )
                    # If no exception, model is accessible
                    available_models.append(model_info)
                except Exception as e:
                    # Check if it's a 404 (model not found) vs other errors
                    error_str = str(e).lower()
                    if "not_found" not in error_str and "404" not in error_str:
                        # Not a 404, might be rate limit or other issue
                        # Include the model anyway to be safe
                        available_models.append(model_info)
                    # If it's a 404, skip this model (not available on this tier)
            
            # If we found at least one accessible model, return the list
            if available_models:
                return available_models
            
            # If no models were accessible, return the full list as fallback
            return known_models
            
        except Exception:
            # If discovery fails entirely, return the full curated list
            return known_models
    
    def _resolve_model_name(self, model: str) -> str:
        """
        Resolve legacy or alias model names to current Claude 4.x identifiers.
        
        Maps deprecated Claude 3.x models to their Claude 4.x equivalents.
        """
        # Map legacy 3.x models to 4.x equivalents
        model_mapping = {
            # Legacy 3.5 models -> 4.x equivalents
            "claude-3-5-sonnet-latest": "claude-opus-4-6",
            "claude-3-5-sonnet-20241022": "claude-opus-4-6",
            "claude-3-5-sonnet-20240620": "claude-opus-4-6",
            "claude-3-5-haiku-latest": "claude-haiku-4-5-20251001",
            "claude-3-5-haiku-20241022": "claude-haiku-4-5-20251001",
            # Legacy 3.x models -> 4.x equivalents
            "claude-3-opus-latest": "claude-opus-4-6",
            "claude-3-opus-20240229": "claude-opus-4-6",
            "claude-3-sonnet-20240229": "claude-sonnet-4-5-20250929",
            "claude-3-haiku-latest": "claude-haiku-4-5-20251001",
            "claude-3-haiku-20240307": "claude-haiku-4-5-20251001",
        }
        return model_mapping.get(model, model)
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """Generate a chat completion using Anthropic Claude."""
        try:
            client = self._get_client(credentials)
            
            # Resolve '-latest' aliases to actual model versions
            resolved_model = self._resolve_model_name(model)
            
            # Use MessageAdapter for Anthropic-specific format
            system_message, conversation_messages = MessageAdapter.to_anthropic(messages)
            
            # Ensure we have at least one user message
            if not conversation_messages:
                raise ProviderError("At least one non-system message is required")
            
            # Map standard parameters to Anthropic equivalents
            mapped_params = ParameterMapper.map_params(kwargs, self.id)
            
            # Claude 4.x requires: use temperature OR top_p, not both
            # We use temperature (more standard for academic use) + top_k for diversity
            request_params = {
                "model": resolved_model,
                "messages": conversation_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_k": mapped_params.get("top_k", 50),
            }
            
            if system_message:
                request_params["system"] = system_message
            
            response = client.messages.create(**request_params)
            
            # Extract response content
            content = ""
            if response.content:
                # Claude returns content as a list of blocks
                content = " ".join(
                    block.text for block in response.content 
                    if hasattr(block, 'text')
                )
            
            # Parse usage
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                }
            
            return ChatResponse(
                content=content,
                model=response.model,
                usage=usage,
                raw=response.model_dump() if hasattr(response, 'model_dump') else None
            )
            
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg:
                raise ProviderAuthenticationError(f"Anthropic authentication failed: {str(e)}")
            elif "rate limit" in error_msg:
                raise ProviderRateLimitError(f"Anthropic rate limit exceeded: {str(e)}")
            elif "context" in error_msg or "maximum" in error_msg:
                raise ProviderContextError(f"Context too long for model {model}: {str(e)}")
            else:
                raise ProviderError(f"Anthropic chat failed: {str(e)}")
