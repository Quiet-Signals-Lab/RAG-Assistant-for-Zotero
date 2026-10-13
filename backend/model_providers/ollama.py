"""
Ollama provider for local LLM inference.

Implements the ModelProvider interface for Ollama, supporting local model execution
without requiring API keys. Communicates with a local Ollama instance via HTTP.
"""

from typing import Dict, Any, List
import requests
from .base import (
    BaseProvider, Message, ChatResponse, ModelInfo,
    ProviderError, ProviderConnectionError, ProviderAuthenticationError,
    MessageAdapter, ParameterMapper
)


class OllamaProvider(BaseProvider):
    """Provider implementation for Ollama local models."""
    
    def __init__(self):
        super().__init__(
            id="ollama",
            label="Ollama (Local)",
            default_model="llama3.2",
            supports_streaming=True,
            requires_api_key=False,
        )
    
    def _get_base_url(self, credentials: Dict[str, Any]) -> str:
        """Get Ollama base URL from credentials or use default."""
        return credentials.get("base_url", "http://localhost:11434")
    
    def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """
        Validate connection to Ollama instance.
        
        For Ollama, we just check if the service is reachable.
        No authentication required.
        """
        base_url = self._get_base_url(credentials)
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except requests.exceptions.ConnectionError:
            raise ProviderConnectionError(
                f"Cannot connect to Ollama at {base_url}. "
                "Make sure Ollama is running (try 'ollama serve')"
            )
        except requests.exceptions.Timeout:
            raise ProviderConnectionError(f"Ollama at {base_url} timed out")
        except Exception as e:
            raise ProviderError(f"Failed to validate Ollama connection: {str(e)}")
    
    def list_models(self, credentials: Dict[str, Any]) -> List[ModelInfo]:
        """
        List available models from Ollama.
        
        Queries the /api/tags endpoint to get all downloaded models.
        """
        base_url = self._get_base_url(credentials)
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for model_data in data.get("models", []):
                name = model_data.get("name", "")
                # Ollama returns models like "llama3.2:latest"
                model_id = name.split(":")[0] if ":" in name else name
                
                models.append(ModelInfo(
                    id=name,  # Use full name with tag
                    name=model_id,  # Display name without tag
                    description=model_data.get("details", {}).get("family", ""),
                    context_length=None,  # Ollama doesn't expose this in tags API
                ))
            
            return models
        except requests.exceptions.RequestException as e:
            raise ProviderConnectionError(f"Failed to list Ollama models: {str(e)}")
    
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
        Generate a chat completion using Ollama.
        
        Uses the /api/chat endpoint for multi-turn conversations.
        Falls back to /api/generate for simple prompts if needed.
        """
        base_url = self._get_base_url(credentials)
        
        # Use MessageAdapter for Ollama format (same as OpenAI)
        ollama_messages = MessageAdapter.to_openai(messages)
        
        # Map standard parameters to Ollama equivalents
        mapped_params = ParameterMapper.map_params(kwargs, self.id)
        
        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                # Generation settings for academic RAG:
                # - top_p: 0.9 prevents low-probability hallucinations via nucleus sampling
                # - top_k: 50 provides vocab diversity for technical language
                # - repeat_penalty: 1.15 prevents citation/concept repetition
                "top_p": mapped_params.get("top_p", 0.9),
                "top_k": mapped_params.get("top_k", 50),
                "repeat_penalty": 1.0 if kwargs.get("response_schema") else mapped_params.get("repeat_penalty", 1.15),
            }
        }
        if kwargs.get("response_schema"):
            # Constrain decoding to the schema, and skip a thinking model's reasoning:
            # the desk clerk wants a short structured answer, not a monologue.
            payload["format"] = kwargs["response_schema"]
            payload["think"] = False
            # Keep the model loaded between searches (Ollama unloads after 5 minutes by
            # default); reloading a 4B model costs several seconds on the next job.
            payload["keep_alive"] = "30m"
        
        try:
            resp = requests.post(
                f"{base_url}/api/chat",
                json=payload,
                timeout=kwargs.get("timeout", 120)
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Extract response content
            message = data.get("message", {})
            content = message.get("content", "")
            
            # Parse usage statistics if available
            usage = None
            if "prompt_eval_count" in data or "eval_count" in data:
                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": (
                        data.get("prompt_eval_count", 0) + 
                        data.get("eval_count", 0)
                    )
                }
            
            return ChatResponse(
                content=content,
                model=model,
                usage=usage,
                raw=data
            )
            
        except requests.exceptions.Timeout:
            raise ProviderError(
                f"Ollama request timed out. Model '{model}' may be slow or not responding."
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ProviderError(
                    f"Model '{model}' not found. Pull it first with: ollama pull {model}"
                )
            raise ProviderError(f"Ollama API error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise ProviderConnectionError(f"Failed to connect to Ollama: {str(e)}")
        except Exception as e:
            raise ProviderError(f"Ollama chat failed: {str(e)}")
