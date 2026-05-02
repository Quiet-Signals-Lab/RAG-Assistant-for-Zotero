"""
Additional LLM providers: Google, Mistral, Groq, and OpenRouter.

These providers use OpenAI-compatible APIs or their own SDKs.
"""

import os

# Suppress gRPC verbose error logging (known issue with google-generativeai)
# Must be set before importing google.generativeai
# NOTE: Main stderr filter for gRPC errors is in backend/main.py
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GRPC_TRACE'] = ''

from typing import Dict, Any, List
from .base import (
    BaseProvider, Message, ChatResponse, ModelInfo,
    ProviderError, ProviderAuthenticationError, ProviderConnectionError,
    ProviderRateLimitError, ProviderContextError,
    MessageAdapter, ParameterMapper
)


class MistralProvider(BaseProvider):
    """
    Provider for Mistral AI.
    Uses OpenAI-compatible API.
    """
    
    def __init__(self):
        super().__init__(
            id="mistral",
            label="Mistral",
            default_model="mistral-large-latest",
            supports_streaming=True,
            requires_api_key=True,
        )
    
    def _get_client(self, credentials: Dict[str, Any]):
        """Get OpenAI-compatible client for Mistral."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ProviderError(
                "OpenAI package required for Mistral. Install with: pip install openai"
            )
        
        api_key = credentials.get("api_key")
        if not api_key:
            raise ProviderAuthenticationError("Mistral API key is required")
        
        # Support custom endpoints (e.g., for proxies or custom deployments)
        # Only use custom base_url if non-empty and non-whitespace
        base_url = credentials.get("base_url", "").strip()
        if not base_url:
            base_url = "https://api.mistral.ai/v1"
        
        return OpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate Mistral API key."""
        try:
            client = self._get_client(credentials)
            client.models.list()
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg or "401" in error_msg:
                raise ProviderAuthenticationError(f"Invalid Mistral API key: {str(e)}")
            raise ProviderError(f"Mistral validation failed: {str(e)}")
    
    def validate_credentials_and_list_models(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate credentials AND return available models dynamically."""
        try:
            client = self._get_client(credentials)
            print(f"[Mistral Provider] Fetching dynamic models via client.models.list()...")
            
            models_response = client.models.list()
            models = [
                ModelInfo(
                    id=model.id,
                    name=model.id,
                    description="Mistral model",
                    context_length=128000 if "large" in model.id.lower() else 32000
                )
                for model in models_response.data
                if model.id  # Skip models without IDs
            ]
            
            # Warn if no models found
            if not models:
                print(f"[Mistral Provider] WARNING: No models returned from endpoint")
            
            for model in models:
                print(f"[Mistral Provider]   Found: {model.id}")
            
            print(f"[Mistral Provider] Successfully discovered {len(models)} models")
            
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
                    "error": f"Invalid Mistral API key: {error_msg}"
                }
            
            return {
                "valid": False,
                "models": [],
                "error": f"Mistral validation failed: {error_msg}"
            }
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """List available Mistral models."""
        try:
            client = self._get_client(credentials)
            models_response = client.models.list()
            
            return [
                ModelInfo(
                    id=model.id,
                    name=model.id,
                    description=None,
                    context_length=None
                )
                for model in models_response.data
            ]
        except Exception:
            # Fallback to known models
            return [
                ModelInfo(
                    id="mistral-large-latest",
                    name="Mistral Large (Latest)",
                    description="Most capable Mistral model",
                    context_length=128000
                ),
                ModelInfo(
                    id="mistral-medium-latest",
                    name="Mistral Medium (Latest)",
                    description="Balanced performance",
                    context_length=32000
                ),
                ModelInfo(
                    id="mistral-small-latest",
                    name="Mistral Small (Latest)",
                    description="Fast and efficient",
                    context_length=32000
                ),
                ModelInfo(
                    id="open-mistral-nemo",
                    name="Mistral Nemo",
                    description="Open source model",
                    context_length=128000
                ),
                ModelInfo(
                    id="open-mixtral-8x7b",
                    name="Mixtral 8x7B",
                    description="Mixture of experts model",
                    context_length=32000
                ),
            ]
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """Generate chat completion using Mistral."""
        try:
            client = self._get_client(credentials)
            
            # Use MessageAdapter for OpenAI-compatible format
            openai_messages = MessageAdapter.to_openai(messages)
            
            # Map standard parameters to Mistral equivalents
            mapped_params = ParameterMapper.map_params(kwargs, self.id)
            
            response = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=mapped_params.get("top_p", 0.9),
            )
            
            content = response.choices[0].message.content or ""
            
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
            error_msg = str(e).lower()
            if "rate limit" in error_msg:
                raise ProviderRateLimitError(f"Mistral rate limit exceeded: {str(e)}")
            elif "context" in error_msg or "maximum" in error_msg:
                raise ProviderContextError(f"Context too long for model {model}: {str(e)}")
            raise ProviderError(f"Mistral chat failed: {str(e)}")


class GoogleProvider(BaseProvider):
    """Provider for Google Gemini models."""
    
    def __init__(self):
        super().__init__(
            id="google",
            label="Google",
            default_model="gemini-1.5-pro-latest",
            supports_streaming=True,
            requires_api_key=True,
        )
    
    def _get_client(self, credentials: Dict[str, Any]):
        """Get Google Generative AI client."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ProviderError(
                "Google Generative AI package not installed. "
                "Install with: pip install google-generativeai"
            )
        
        api_key = credentials.get("api_key")
        if not api_key:
            raise ProviderAuthenticationError("Google API key is required")
        
        # Log SDK version for debugging
        print(f"[Google Provider] Using google-generativeai version: {genai.__version__ if hasattr(genai, '__version__') else 'unknown'}")
        print(f"[Google Provider] API key present: {bool(api_key)} (length: {len(api_key) if api_key else 0})")
        
        genai.configure(api_key=api_key)
        return genai
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate Google API key."""
        try:
            genai = self._get_client(credentials)
            # List models as validation
            list(genai.list_models())
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "api key" in error_msg or "authentication" in error_msg or "401" in error_msg:
                raise ProviderAuthenticationError(f"Invalid Google API key: {str(e)}")
            raise ProviderError(f"Google validation failed: {str(e)}")
    
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
            genai = self._get_client(credentials)
            
            # List all models accessible to this API key
            models = []
            print(f"[Google Provider] Fetching dynamic models via genai.list_models()...")
            
            try:
                # Attempt dynamic model discovery
                model_list = list(genai.list_models())
                
                for model in model_list:
                    # Filter for models that support generateContent (chat/reasoning)
                    if hasattr(model, 'supported_generation_methods') and 'generateContent' in model.supported_generation_methods:
                        # Extract model ID (remove 'models/' prefix if present)
                        model_id = model.name.replace("models/", "") if hasattr(model, 'name') else str(model)
                        
                        # Detect capabilities based on model metadata
                        capabilities = self._detect_capabilities(model)
                        
                        # Get context window (input token limit)
                        context_window = getattr(model, 'input_token_limit', 32768)
                        
                        # Create friendly display name
                        display_name = getattr(model, 'display_name', None) or model_id
                        
                        # Get description if available
                        description = getattr(model, 'description', None) or self._generate_description(model_id, capabilities)
                        
                        models.append(ModelInfo(
                            id=model_id,
                            name=display_name,
                            description=description,
                            context_length=context_window
                        ))
                        
                        print(f"[Google Provider]   Found: {model_id} (ctx: {context_window})")
                
                # Sort models by name for consistent UI display
                if models:
                    models.sort(key=lambda m: m.name)
                    print(f"[Google Provider] Successfully discovered {len(models)} models")
                else:
                    # No models found via API, use fallback
                    print(f"[Google Provider] No models found via API, using fallback")
                    raise Exception("No models returned from API")
                    
            except Exception as list_error:
                # If dynamic discovery fails (e.g., gRPC errors), use static fallback
                # but still validate the credentials work
                print(f"[Google Provider] Dynamic discovery failed ({type(list_error).__name__}), using static fallback")
                
                # Use static fallback models
                models = self._get_fallback_models()
            
            return {
                "valid": True,
                "models": models,
                "message": f"Success! Found {len(models)} models available."
            }
            
        except Exception as e:
            error_msg = str(e)
            error_msg_lower = error_msg.lower()
            
            if "api key" in error_msg_lower or "authentication" in error_msg_lower or "401" in error_msg_lower:
                return {
                    "valid": False,
                    "models": [],
                    "error": f"Invalid Google API key: {error_msg}"
                }
            
            return {
                "valid": False,
                "models": [],
                "error": f"Google validation failed: {error_msg}"
            }
    
    def _get_fallback_models(self) -> List[ModelInfo]:
        """Return static fallback model list when dynamic discovery fails."""
        return [
            ModelInfo(
                id="gemini-1.5-pro-latest",
                name="Gemini 1.5 Pro (Latest)",
                description="Most capable model, auto-updated",
                context_length=2000000
            ),
            ModelInfo(
                id="gemini-1.5-flash-latest",
                name="Gemini 1.5 Flash (Latest)",
                description="Fast and efficient, auto-updated",
                context_length=1000000
            ),
            ModelInfo(
                id="gemini-1.5-pro",
                name="Gemini 1.5 Pro (Stable)",
                description="Stable version, not auto-updated",
                context_length=2000000
            ),
            ModelInfo(
                id="gemini-1.5-flash",
                name="Gemini 1.5 Flash (Stable)",
                description="Fast stable version",
                context_length=1000000
            ),
            ModelInfo(
                id="gemini-2.0-flash-exp",
                name="Gemini 2.0 Flash (Experimental)",
                description="Latest experimental model",
                context_length=1000000
            ),
        ]
    
    def _detect_capabilities(self, model) -> List[str]:
        """Detect model capabilities from metadata."""
        capabilities = ["chat"]
        
        # Check for reasoning/advanced capabilities
        if hasattr(model, 'supported_generation_methods'):
            if 'generateContent' in model.supported_generation_methods:
                capabilities.append("reasoning")
        
        # Check for vision/multimodal support
        model_name_lower = model.name.lower()
        if 'vision' in model_name_lower:
            capabilities.append("vision")
        
        # Check description for multimodal mentions
        if hasattr(model, 'description'):
            description_lower = getattr(model, 'description', '').lower()
            if 'multimodal' in description_lower or 'image' in description_lower:
                if "vision" not in capabilities:
                    capabilities.append("vision")
        
        return capabilities
    
    def _generate_description(self, model_id: str, capabilities: List[str]) -> str:
        """Generate a description for a model based on its ID and capabilities."""
        # Parse common patterns
        if 'pro' in model_id.lower():
            desc = "Most capable model"
        elif 'flash' in model_id.lower():
            desc = "Fast and efficient model"
        else:
            desc = "Gemini model"
        
        # Add stability info
        if 'latest' in model_id.lower():
            desc += ", auto-updated"
        elif 'exp' in model_id.lower():
            desc += ", experimental"
        else:
            desc += ", stable version"
        
        return desc
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """List available Google models.
        
        If credentials are provided and valid, returns dynamic model list.
        Otherwise, returns static fallback list.
        """
        # Try dynamic discovery if credentials provided
        if credentials and credentials.get("api_key"):
            try:
                result = self.validate_credentials_and_list_models(credentials)
                if result["valid"] and result["models"]:
                    print(f"[Google Provider] Using {len(result['models'])} dynamically discovered models")
                    return result["models"]
            except Exception as e:
                print(f"[Google Provider] Dynamic model discovery failed: {e}, using static fallback")
        
        # Fallback to static list if dynamic discovery fails or no credentials
        print("[Google Provider] Using static fallback model list")
        return self._get_fallback_models()
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """Generate chat completion using Google Gemini."""
        try:
            genai = self._get_client(credentials)
            
            # Log the exact model being used
            print(f"[Google Provider] chat() called with model='{model}'")
            
            # Validate model name format - Gemini models should not have "models/" prefix here
            # The SDK will add it automatically
            if model.startswith("models/"):
                model = model.replace("models/", "")
                print(f"[Google Provider] Stripped 'models/' prefix, using: '{model}'")
            
            # Use MessageAdapter for Gemini-specific format
            system_instruction, gemini_history = MessageAdapter.to_gemini(messages)
            
            # Map standard parameters to Google equivalents
            mapped_params = ParameterMapper.map_params(kwargs, self.id)
            
            # Configure safety settings to prevent over-blocking
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                },
            ]
            
            # Create model instance with system instruction
            print(f"[Google Provider] Creating GenerativeModel with model='{model}'")
            print(f"[Google Provider] System instruction length: {len(system_instruction) if system_instruction else 0}")
            print(f"[Google Provider] Number of history messages: {len(gemini_history)}")
            print(f"[Google Provider] Temperature: {temperature}, Max tokens: {max_tokens}")
            
            # Debug: Print first message preview
            if gemini_history:
                first_msg = gemini_history[0]
                preview = str(first_msg.get('parts', [''])[0])[:200] if first_msg.get('parts') else 'No parts'
                print(f"[Google Provider] First message role: {first_msg.get('role')}, preview: {preview}...")
            
            try:
                model_instance = genai.GenerativeModel(
                    model,
                    system_instruction=system_instruction,
                    safety_settings=safety_settings
                )
                print(f"[Google Provider] Model instance created successfully")
            except Exception as model_error:
                print(f"[Google Provider] ERROR creating model: {type(model_error).__name__}: {model_error}")
                raise
            
            # Use adapted Gemini message format
            # Gemini expects alternating user/model turns in chat history
            print(f"[Google Provider] Calling API with {len(gemini_history)} message(s)...")
            
            if len(gemini_history) == 1 and gemini_history[0]["role"] == "user":
                # Single turn - use generate_content
                print(f"[Google Provider] Using generate_content (single turn)")
                content_to_send = gemini_history[0]["parts"][0]
                print(f"[Google Provider] Content length: {len(content_to_send)} chars")
                
                # Try to add request_options with timeout if available
                request_kwargs = {}
                try:
                    import google.ai.generativelanguage as glm
                    request_options = glm.types.RequestOptions(timeout=120)
                    request_kwargs['request_options'] = request_options
                    print(f"[Google Provider] Using 120s timeout")
                except (ImportError, AttributeError) as to_err:
                    print(f"[Google Provider] Could not set timeout: {to_err}")
                
                response = model_instance.generate_content(
                    content_to_send,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                        "top_p": mapped_params.get("top_p", 0.95),
                        "top_k": mapped_params.get("top_k", 40),
                    },
                    **request_kwargs
                )
                print(f"[Google Provider] generate_content completed")
            else:
                # Multi-turn - use chat with history
                print(f"[Google Provider] Using start_chat (multi-turn)")
                
                request_kwargs = {}
                try:
                    import google.ai.generativelanguage as glm
                    request_options = glm.types.RequestOptions(timeout=120)
                    request_kwargs['request_options'] = request_options
                    print(f"[Google Provider] Using 120s timeout")
                except (ImportError, AttributeError) as to_err:
                    print(f"[Google Provider] Could not set timeout: {to_err}")
                
                chat = model_instance.start_chat(history=gemini_history[:-1])
                response = chat.send_message(
                    gemini_history[-1]["parts"][0],
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                        "top_p": mapped_params.get("top_p", 0.95),
                        "top_k": mapped_params.get("top_k", 40),
                    },
                    **request_kwargs
                )
                print(f"[Google Provider] send_message completed")
            
            # Check if response was blocked by safety filters
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                if hasattr(feedback, 'block_reason') and feedback.block_reason:
                    block_reason = str(feedback.block_reason)
                    print(f"[Google Provider] WARNING: Response blocked by safety filter: {block_reason}")
                    raise ProviderError(f"Google blocked the request: {block_reason}")
            
            # Extract text from response
            print(f"[Google Provider] Extracting content from response...")
            content = ""
            if hasattr(response, 'text'):
                content = response.text
                print(f"[Google Provider] Got content via .text attribute ({len(content)} chars)")
            elif hasattr(response, 'candidates') and response.candidates:
                # Extract from candidates if text attribute not available
                print(f"[Google Provider] Extracting from candidates ({len(response.candidates)} candidates)")
                candidate = response.candidates[0]
                
                # Check if candidate was blocked
                if hasattr(candidate, 'finish_reason'):
                    finish_reason = str(candidate.finish_reason)
                    print(f"[Google Provider] Finish reason: {finish_reason}")
                    if 'SAFETY' in finish_reason or 'BLOCKED' in finish_reason:
                        raise ProviderError(f"Google blocked the response: {finish_reason}")
                
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    content = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text'))
                    print(f"[Google Provider] Got content from candidate.content.parts ({len(content)} chars)")
            
            if not content:
                print(f"[Google Provider] ERROR: No content in response!")
                print(f"[Google Provider] Response type: {type(response)}")
                print(f"[Google Provider] Response attributes: {dir(response)}")
                raise ProviderError("No content in Google Gemini response")
            
            # Google usage metadata
            usage = None
            if hasattr(response, 'usage_metadata'):
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0),
                }
            
            return ChatResponse(
                content=content,
                model=model,
                usage=usage,
                raw=None  # Can't easily serialize Gemini response
            )
        except Exception as e:
            # Provide more detailed error information
            error_msg = str(e)
            error_type = type(e).__name__
            
            print(f"[Google Provider] ERROR: {error_type}: {error_msg}")
            
            if hasattr(e, 'message'):
                error_msg = e.message
            error_msg_lower = error_msg.lower()
            
            # Check for specific error types
            if "timeout" in error_msg_lower or "timed out" in error_msg_lower:
                raise ProviderError(f"Google Gemini request timed out after 120 seconds: {error_msg}")
            elif "rate limit" in error_msg_lower or "quota" in error_msg_lower or "429" in error_msg_lower:
                raise ProviderRateLimitError(f"Google Gemini rate limit exceeded: {error_msg}")
            elif "context" in error_msg_lower or "token" in error_msg_lower or "too long" in error_msg_lower:
                raise ProviderContextError(f"Context too long for model {model}: {error_msg}")
            elif "api key" in error_msg_lower or "authentication" in error_msg_lower or "401" in error_msg_lower:
                raise ProviderAuthenticationError(f"Google API authentication failed: {error_msg}")
            elif "blocked" in error_msg_lower or "safety" in error_msg_lower:
                raise ProviderError(f"Google blocked the request due to safety filters: {error_msg}")
            
            raise ProviderError(f"Google Gemini chat failed ({error_type}): {error_msg}")


class GroqProvider(BaseProvider):
    """
    Provider for Groq (fast inference for open models).
    Uses OpenAI-compatible API.
    """
    
    def __init__(self):
        super().__init__(
            id="groq",
            label="Groq",
            default_model="llama-3.3-70b-versatile",
            supports_streaming=True,
            requires_api_key=True,
        )
    
    def _get_client(self, credentials: Dict[str, Any]):
        """Get OpenAI-compatible client for Groq."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ProviderError(
                "OpenAI package required for Groq. Install with: pip install openai"
            )
        
        api_key = credentials.get("api_key")
        if not api_key:
            raise ProviderAuthenticationError("Groq API key is required")
        
        # Support custom endpoints (e.g., for proxies or custom deployments)
        base_url = credentials.get("base_url", "https://api.groq.com/openai/v1")
        # Edge case: if base_url is empty string or whitespace, use default
        if isinstance(base_url, str):
            base_url = base_url.strip()
        if not base_url:
            base_url = "https://api.groq.com/openai/v1"
        
        return OpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate Groq API key."""
        try:
            client = self._get_client(credentials)
            client.models.list()
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg or "401" in error_msg:
                raise ProviderAuthenticationError(f"Invalid Groq API key: {str(e)}")
            raise ProviderError(f"Groq validation failed: {str(e)}")
    
    def validate_credentials_and_list_models(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate credentials AND return available models dynamically."""
        try:
            client = self._get_client(credentials)
            print(f"[Groq Provider] Fetching dynamic models via client.models.list()...")
            
            models_response = client.models.list()
            models = [
                ModelInfo(
                    id=model.id,
                    name=model.id,
                    description="Groq model",
                    context_length=32768
                )
                for model in models_response.data
                if model.id  # Edge case: skip models without IDs
            ]
            
            # Edge case: warn if no models returned
            if not models:
                print(f"[Groq Provider] WARNING: No models returned from endpoint")
            
            for model in models:
                print(f"[Groq Provider]   Found: {model.id}")
            
            print(f"[Groq Provider] Successfully discovered {len(models)} models")
            
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
                    "error": f"Invalid Groq API key: {error_msg}"
                }
            
            return {
                "valid": False,
                "models": [],
                "error": f"Groq validation failed: {error_msg}"
            }
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """List available Groq models."""
        try:
            client = self._get_client(credentials)
            models_response = client.models.list()
            
            return [
                ModelInfo(
                    id=model.id,
                    name=model.id,
                    description=None,
                    context_length=None
                )
                for model in models_response.data
            ]
        except Exception:
            # Fallback to known models
            return [
                ModelInfo(
                    id="llama-3.3-70b-versatile",
                    name="Llama 3.3 70B",
                    description="Most capable Llama model",
                    context_length=32768
                ),
                ModelInfo(
                    id="llama-3.1-8b-instant",
                    name="Llama 3.1 8B",
                    description="Fast and efficient",
                    context_length=131072
                ),
            ]
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """Generate chat completion using Groq."""
        try:
            client = self._get_client(credentials)
            
            # Use MessageAdapter for OpenAI-compatible format
            openai_messages = MessageAdapter.to_openai(messages)
            
            # Map standard parameters to Groq equivalents
            mapped_params = ParameterMapper.map_params(kwargs, self.id)
            
            # 2025 best practices: top_p=0.9 for nucleus sampling, frequency_penalty for citation diversity
            response = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=mapped_params.get("top_p", 0.9),
                frequency_penalty=mapped_params.get("frequency_penalty", 0.3),
            )
            
            content = response.choices[0].message.content or ""
            
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
            error_msg = str(e).lower()
            if "rate limit" in error_msg:
                raise ProviderRateLimitError(f"Groq rate limit exceeded: {str(e)}")
            elif "context" in error_msg or "maximum" in error_msg:
                raise ProviderContextError(f"Context too long for model {model}: {str(e)}")
            raise ProviderError(f"Groq chat failed: {str(e)}")


class OpenRouterProvider(BaseProvider):
    """
    Provider for OpenRouter (unified API for many models).
    Uses OpenAI-compatible API.
    """
    
    def __init__(self):
        super().__init__(
            id="openrouter",
            label="OpenRouter",
            default_model="anthropic/claude-3.5-sonnet",
            supports_streaming=True,
            requires_api_key=True,
        )
    
    def _get_client(self, credentials: Dict[str, Any]):
        """Get OpenAI-compatible client for OpenRouter."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ProviderError(
                "OpenAI package required for OpenRouter. Install with: pip install openai"
            )
        
        api_key = credentials.get("api_key")
        if not api_key:
            raise ProviderAuthenticationError("OpenRouter API key is required")
        
        # Support custom endpoints (e.g., for proxies or custom deployments)
        base_url = credentials.get("base_url", "https://openrouter.ai/api/v1")
        # Edge case: if base_url is empty string or whitespace, use default
        if isinstance(base_url, str):
            base_url = base_url.strip()
        if not base_url:
            base_url = "https://openrouter.ai/api/v1"
        
        return OpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validate OpenRouter API key."""
        try:
            client = self._get_client(credentials)
            client.models.list()
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg or "401" in error_msg:
                raise ProviderAuthenticationError(f"Invalid OpenRouter API key: {str(e)}")
            raise ProviderError(f"OpenRouter validation failed: {str(e)}")
    
    def validate_credentials_and_list_models(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate credentials AND return available models dynamically."""
        try:
            client = self._get_client(credentials)
            print(f"[OpenRouter Provider] Fetching dynamic models via client.models.list()...")
            
            models_response = client.models.list()
            # OpenRouter has many models, return popular ones (limit to 30)
            models = [
                ModelInfo(
                    id=model.id,
                    name=model.id,
                    description="Available via OpenRouter",
                    context_length=None
                )
                for model in models_response.data[:30]
                if model.id  # Edge case: skip models without IDs
            ]
            
            # Edge case: warn if no models returned
            if not models:
                print(f"[OpenRouter Provider] WARNING: No models returned from endpoint")
            
            for model in models[:10]:  # Log first 10
                print(f"[OpenRouter Provider]   Found: {model.id}")
            if len(models) > 10:
                print(f"[OpenRouter Provider]   ... and {len(models) - 10} more")
            
            print(f"[OpenRouter Provider] Successfully discovered {len(models)} models")
            
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
                    "error": f"Invalid OpenRouter API key: {error_msg}"
                }
            
            return {
                "valid": False,
                "models": [],
                "error": f"OpenRouter validation failed: {error_msg}"
            }
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """List available OpenRouter models."""
        try:
            client = self._get_client(credentials)
            models_response = client.models.list()
            
            # OpenRouter has many models, return popular ones; skip entries with no ID
            models = [
                ModelInfo(
                    id=model.id,
                    name=model.id,
                    description=None,
                    context_length=None
                )
                for model in models_response.data[:20]  # Limit to first 20
                if model.id  # Skip models without IDs
            ]
            if models:
                return models
            # Fall through to fallback if API returned nothing useful
        except Exception:
            pass
        # Fallback to known popular models
        return [
                ModelInfo(
                    id="anthropic/claude-3.5-sonnet",
                    name="Claude 3.5 Sonnet",
                    description="Via OpenRouter",
                    context_length=200000
                ),
                ModelInfo(
                    id="openai/gpt-4-turbo",
                    name="GPT-4 Turbo",
                    description="Via OpenRouter",
                    context_length=128000
                ),
            ]
    
    def chat(
        self,
        credentials: Dict[str, Any],
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ) -> ChatResponse:
        """Generate chat completion using OpenRouter."""
        try:
            client = self._get_client(credentials)
            
            # Use MessageAdapter for OpenAI-compatible format
            openai_messages = MessageAdapter.to_openai(messages)
            
            # Map standard parameters to OpenRouter equivalents
            mapped_params = ParameterMapper.map_params(kwargs, self.id)
            
            # 2025 best practices: top_p=0.9 for nucleus sampling, frequency_penalty for citation diversity
            response = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=mapped_params.get("top_p", 0.9),
                frequency_penalty=mapped_params.get("frequency_penalty", 0.3),
            )
            
            content = response.choices[0].message.content or ""
            
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
            error_msg = str(e).lower()
            if "rate limit" in error_msg:
                raise ProviderRateLimitError(f"OpenRouter rate limit exceeded: {str(e)}")
            elif "context" in error_msg or "maximum" in error_msg:
                raise ProviderContextError(f"Context too long for model {model}: {str(e)}")
            raise ProviderError(f"OpenRouter chat failed: {str(e)}")
