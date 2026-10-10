"""
OpenAI provider for GPT models.

Implements the ModelProvider interface for OpenAI's API, supporting
GPT-4, GPT-3.5, and other OpenAI models.
"""

import re
import httpx
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from .base import (
    BaseProvider, Message, ChatResponse, ModelInfo,
    ProviderError, ProviderAuthenticationError, ProviderConnectionError,
    ProviderRateLimitError, ProviderContextError,
    MessageAdapter, ParameterMapper
)
import logging

logger = logging.getLogger(__name__)


@dataclass
class _ModelStub:
    """Lightweight proxy for model entries returned by raw HTTP model list responses."""
    id: str


class OpenAIProvider(BaseProvider):
    """Provider implementation for OpenAI models."""
    
    def __init__(self):
        super().__init__(
            id="openai",
            label="OpenAI",
            default_model="gpt-4o-mini",
            supports_streaming=True,
            requires_api_key=True,
        )
        self._client = None
    
    def _get_client(self, credentials: Dict[str, Any]):
        """Get or create OpenAI client with credentials."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ProviderError(
                "OpenAI package not installed. Install with: pip install openai"
            )
        
        api_key = credentials.get("api_key")
        if not api_key:
            raise ProviderAuthenticationError("OpenAI API key is required")
        
        # For custom endpoints - only use if non-empty and non-whitespace
        base_url = credentials.get("base_url", "").strip()
        return OpenAI(api_key=api_key, base_url=base_url if base_url else None)
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate OpenAI API key by making a test request."""
        try:
            client = self._get_client(credentials)
            # Try to list models as a validation check
            client.models.list()
            return True
        except ImportError as e:
            raise ProviderError(str(e))
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg or "401" in error_msg:
                raise ProviderAuthenticationError(f"Invalid OpenAI API key: {str(e)}")
            elif "connection" in error_msg or "network" in error_msg:
                raise ProviderConnectionError(f"Cannot connect to OpenAI: {str(e)}")
            else:
                raise ProviderError(f"OpenAI validation failed: {str(e)}")
    
    def _extract_model_id(self, raw_id: str) -> str:
        """Extract a usable model name from Azure ML resource paths.

        azureml://registries/azure-openai/models/gpt-4o/versions/2 -> gpt-4o
        """
        match = re.search(r'/models/([^/]+)/versions/', raw_id)
        if match:
            return match.group(1)
        return raw_id

    def _list_models_raw(self, credentials: Dict[str, Any]):
        """Fetch models via raw HTTP for endpoints that don't follow OpenAI response format."""
        base_url = credentials.get("base_url", "").rstrip("/")
        api_key = credentials.get("api_key", "")
        resp = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # Handle both {"data": [...]} and plain [...] responses
        items = data if isinstance(data, list) else data.get("data", [])
        # Normalize model IDs — replace Azure ML paths with simple names
        normalized = []
        for m in items:
            if isinstance(m, dict):
                raw_id = m.get("id", "")
                m = dict(m)
                m["id"] = self._extract_model_id(raw_id)
            normalized.append(m)
        return normalized

    def validate_credentials_and_list_models(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate credentials AND return available models dynamically.

        Returns:
            {
                "valid": bool,
                "models": List[ModelInfo],
                "message": str
            }
        """
        try:
            client = self._get_client(credentials)
            logger.info(f"[OpenAI Provider] Fetching dynamic models via client.models.list()...")

            try:
                models_response = client.models.list()
                raw_models = list(models_response.data)
            except (AttributeError, TypeError):
                # Custom endpoint returned a plain list — fall back to raw HTTP
                logger.info(f"[OpenAI Provider] SDK parse failed, falling back to raw HTTP model fetch")
                raw_items = self._list_models_raw(credentials)
                raw_models = [_ModelStub(id=m.get("id", m) if isinstance(m, dict) else m) for m in raw_items]

            available_model_ids = {model.id for model in raw_models}
            
            # Define curated models for academic use
            curated_models = {
                "gpt-4o": ModelInfo(
                    id="gpt-4o",
                    name="GPT-4o",
                    description="Most capable model, best for complex reasoning",
                    context_length=128000
                ),
                "gpt-4o-mini": ModelInfo(
                    id="gpt-4o-mini",
                    name="GPT-4o Mini",
                    description="Fast and affordable, good for most tasks",
                    context_length=128000
                ),
                "o1-preview": ModelInfo(
                    id="o1-preview",
                    name="o1 Preview",
                    description="Advanced reasoning model",
                    context_length=128000
                ),
                "o1-mini": ModelInfo(
                    id="o1-mini",
                    name="o1 Mini",
                    description="Fast reasoning model",
                    context_length=128000
                ),
                "gpt-4-turbo": ModelInfo(
                    id="gpt-4-turbo",
                    name="GPT-4 Turbo",
                    description="Previous generation flagship model",
                    context_length=128000
                ),
                "gpt-3.5-turbo": ModelInfo(
                    id="gpt-3.5-turbo",
                    name="GPT-3.5 Turbo",
                    description="Fast and economical",
                    context_length=16385
                ),
            }
            
            # Check if using custom endpoint (non-empty, non-whitespace base_url)
            base_url = credentials.get("base_url", "").strip()
            is_custom_endpoint = bool(base_url)
            
            if is_custom_endpoint:
                # For custom endpoints, return ALL models without filtering
                # (they may not follow OpenAI naming conventions)
                models = [
                    ModelInfo(
                        id=model.id,
                        name=model.id,
                        description="Custom endpoint model",
                        context_length=None
                    )
                    for model in raw_models
                ]

                # Warn if no models found
                if not models:
                    logger.info(f"[OpenAI Provider] WARNING: Custom endpoint returned 0 models")
            else:
                # For official OpenAI API, use curated list
                models = [info for model_id, info in curated_models.items() if model_id in available_model_ids]

                # If no curated models found, include all GPT/o1 models
                if not models:
                    models = [
                        ModelInfo(
                            id=model.id,
                            name=model.id,
                            description="OpenAI model",
                            context_length=None
                        )
                        for model in raw_models
                        if "gpt" in model.id.lower() or "o1" in model.id.lower()
                    ]
                    
                    # Warn if still no models found
                    if not models:
                        logger.info(f"[OpenAI Provider] WARNING: No GPT or o1 models found in API response")
            
            for model in models:
                logger.info(f"[OpenAI Provider]   Found: {model.id}")
            
            logger.info(f"[OpenAI Provider] Successfully discovered {len(models)} models")
            
            return {
                "valid": True,
                "models": models,
                "message": f"Success! Found {len(models)} models available."
            }
            
        except Exception as e:
            error_msg = str(e)
            error_msg_lower = error_msg.lower()
            
            if "authentication" in error_msg_lower or "api key" in error_msg_lower or "401" in error_msg_lower:
                return {
                    "valid": False,
                    "models": [],
                    "error": f"Invalid OpenAI API key: {error_msg}"
                }
            
            return {
                "valid": False,
                "models": [],
                "error": f"OpenAI validation failed: {error_msg}"
            }
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """
        List available OpenAI models.
        
        Returns a curated list of useful models rather than the full API response.
        """
        try:
            client = self._get_client(credentials)
            # Get models from API
            try:
                models_response = client.models.list()
                raw_models = list(models_response.data)
            except (AttributeError, TypeError):
                logger.info(f"[OpenAI Provider] SDK parse failed, falling back to raw HTTP model fetch")
                raw_items = self._list_models_raw(credentials)
                raw_models = [_ModelStub(id=m.get("id", m) if isinstance(m, dict) else m) for m in raw_items]

            # Define curated models we care about for academic use
            curated_models = {
                "gpt-4o": ModelInfo(
                    id="gpt-4o",
                    name="GPT-4o",
                    description="Most capable model, best for complex reasoning",
                    context_length=128000
                ),
                "gpt-4o-mini": ModelInfo(
                    id="gpt-4o-mini",
                    name="GPT-4o Mini",
                    description="Fast and affordable, good for most tasks",
                    context_length=128000
                ),
                "gpt-4-turbo": ModelInfo(
                    id="gpt-4-turbo",
                    name="GPT-4 Turbo",
                    description="Previous generation flagship model",
                    context_length=128000
                ),
                "gpt-3.5-turbo": ModelInfo(
                    id="gpt-3.5-turbo",
                    name="GPT-3.5 Turbo",
                    description="Fast and economical",
                    context_length=16385
                ),
            }
            
            # Check if using custom endpoint (non-empty, non-whitespace base_url)
            base_url = credentials.get("base_url", "").strip()
            is_custom_endpoint = bool(base_url)
            
            if is_custom_endpoint:
                # For custom endpoints, return ALL models without filtering
                # (they may not follow OpenAI naming conventions)
                result = [
                    ModelInfo(
                        id=model.id,
                        name=model.id,
                        description="Custom endpoint model",
                        context_length=None
                    )
                    for model in raw_models
                ]

                # Warn if no models found from custom endpoint
                if not result:
                    logger.info(f"[OpenAI Provider] WARNING: Custom endpoint at {base_url} returned 0 models")

                return result
            else:
                # For official OpenAI API, use curated list with filtering
                available_model_ids = {model.id for model in raw_models}
                available_models = [
                    info for model_id, info in curated_models.items()
                    if model_id in available_model_ids
                ]
                
                # If we found any of our curated models, return those
                # Otherwise, return all GPT models from the API
                if available_models:
                    return available_models
                else:
                    # Fallback: return all gpt models
                    fallback = [
                        ModelInfo(
                            id=model.id,
                            name=model.id,
                            description=None,
                            context_length=None
                        )
                        for model in raw_models
                        if "gpt" in model.id.lower()
                    ]
                    
                    # Warn if still no models found
                    if not fallback:
                        logger.info(f"[OpenAI Provider] WARNING: No GPT models found in official OpenAI API response")
                    
                    return fallback
                
        except Exception as e:
            raise ProviderError(f"Failed to list OpenAI models: {str(e)}")
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """Generate a chat completion using OpenAI."""
        try:
            client = self._get_client(credentials)
            
            # Use MessageAdapter for OpenAI format
            openai_messages = MessageAdapter.to_openai(messages)
            
            # Map standard parameters to OpenAI equivalents
            mapped_params = ParameterMapper.map_params(kwargs, self.id)
            
            # Make the API call with the generation settings used for academic RAG
            # top_p: 0.9 for nucleus sampling (prevents low-prob hallucinations)
            # frequency_penalty: 0.3 reduces citation/concept repetition
            response = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=mapped_params.get("top_p", 0.9),
                frequency_penalty=mapped_params.get("frequency_penalty", 0.3),
                presence_penalty=kwargs.get("presence_penalty", 0.0),
            )
            
            # Extract response
            content = response.choices[0].message.content or ""
            
            # Parse usage
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            
            return ChatResponse(
                content=content,
                model=response.model,
                usage=usage,
                raw=response.model_dump() if hasattr(response, 'model_dump') else None
            )
            
        except Exception as e:
            # Import OpenAI error types for specific handling
            try:
                from openai import (
                    AuthenticationError, 
                    RateLimitError, 
                    APIConnectionError,
                    BadRequestError
                )
                
                # Check specific error types first
                if isinstance(e, AuthenticationError):
                    raise ProviderAuthenticationError(f"OpenAI authentication failed: {str(e)}")
                elif isinstance(e, RateLimitError):
                    # Extract more specific message if available
                    error_msg = str(e)
                    if "quota" in error_msg.lower() or "insufficient_quota" in error_msg.lower():
                        raise ProviderRateLimitError(
                            "OpenAI quota exceeded. Please check your plan and billing at https://platform.openai.com/account/billing"
                        )
                    raise ProviderRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
                elif isinstance(e, APIConnectionError):
                    raise ProviderConnectionError(f"Cannot connect to OpenAI: {str(e)}")
                elif isinstance(e, BadRequestError):
                    error_msg = str(e).lower()
                    if "context" in error_msg or "maximum" in error_msg or "too long" in error_msg:
                        raise ProviderContextError(f"Context too long for model {model}: {str(e)}")
            except ImportError:
                pass  # Fall back to string matching
            
            # Fall back to string-based error detection
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg or "401" in error_msg:
                raise ProviderAuthenticationError(f"OpenAI authentication failed: {str(e)}")
            elif "quota" in error_msg or "insufficient_quota" in error_msg or "429" in error_msg:
                raise ProviderRateLimitError(
                    "OpenAI quota exceeded. Please check your plan and billing at https://platform.openai.com/account/billing"
                )
            elif "rate limit" in error_msg:
                raise ProviderRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
            elif "context length" in error_msg or "maximum context" in error_msg:
                raise ProviderContextError(f"Context too long for model {model}: {str(e)}")
            else:
                raise ProviderError(f"OpenAI chat failed: {str(e)}")
