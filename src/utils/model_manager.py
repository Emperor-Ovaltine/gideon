import json
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger('model_manager')

class ProviderManager:
    """Manages multiple AI providers and their models."""
    
    # Bumped when the shape or meaning of cached fields changes, so stale
    # files are discarded instead of migrated. v3: OpenRouter cached models include output modalities/modality for video filtering.
    CACHE_VERSION = 3

    def __init__(self, openrouter_client, openai_client, ai_horde_client, data_directory: str):
        self.providers = {
            "openrouter": openrouter_client,
            "openai": openai_client,
            "ai_horde": ai_horde_client
        }
        self.data_directory = data_directory
        # Each provider gets its own cache slot; a single shared one meant
        # fetching one provider's list evicted the other's.
        self.models_by_provider: Dict[str, Dict[str, Any]] = {}
        self.last_update: Dict[str, datetime] = {}
        self.cache_duration = timedelta(hours=12)

    def parse_model_id(self, model_id: str) -> Tuple[str, str]:
        """Parse provider/model_name or provider:model_name format into (provider, model_name) tuple."""
        if not model_id:
            raise ValueError("Model ID cannot be empty")

        has_slash = "/" in model_id
        has_colon = ":" in model_id

        # Reject mixed separators immediately
        if has_slash and has_colon:
             # Allow colon only if it's clearly part of the model name itself (after the first slash)
             first_slash_index = model_id.find("/")
             first_colon_index = model_id.find(":")
             if first_colon_index < first_slash_index:
                  raise ValueError(f"Invalid model ID format '{model_id}'. Cannot have ':' before the first '/'. Use 'provider/model_name'.")
             # If colon is after slash, assume it's part of the model name (e.g., openrouter/anthropic/claude-3-opus:beta)

        # Prioritize '/' separator (standard OpenRouter format)
        if has_slash:
            parts = model_id.split("/", 1)
            if len(parts) == 2 and parts[0]: # Ensure provider part is not empty
                provider, model_name = parts
                if model_name: # Ensure model part is not empty
                    return provider.lower(), model_name
        
        # Handle ':' only if '/' was not present
        if has_colon:
            parts = model_id.split(":", 1)
            if len(parts) == 2 and parts[0]: # Ensure provider part is not empty
                provider, model_name = parts
                if model_name: # Ensure model part is not empty
                    logger.warning(f"Using ':' separator for model ID '{model_id}'. Prefer 'provider/model_name' format.")
                    return provider.lower(), model_name

        # If no separator, assume it's an OpenRouter model for backward compatibility.
        logger.warning(f"Model ID '{model_id}' lacks provider prefix, assuming 'openrouter'. Use 'openrouter/{model_id}' for clarity.")
        return "openrouter", model_id
        
    async def get_providers(self) -> List[str]:
        """Get list of available providers."""
        return list(self.providers.keys())
        
    async def get_models(self, provider: str, force_refresh: bool = False) -> List[str]:
        """Get available models for a specific provider."""
        logger.debug(f"get_models called for provider: '{provider}' (force_refresh={force_refresh})") # Add logging
        client = self.providers.get(provider)
        if not client:
            logger.error(f"Client lookup failed for provider: '{provider}'") # Add logging
            raise ValueError(f"Provider '{provider}' not found")

        models_data = await self._get_provider_data(provider, force_refresh)
        if not models_data:
            return []

        return [model["id"] for model in models_data.get("models", []) if "id" in model]

    async def _get_provider_data(self, provider: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Return a provider's cached model data, refreshing it when needed."""
        if (force_refresh
                or provider not in self.models_by_provider
                or self._is_cache_stale(provider)):
            await self._refresh_models(provider)

        models_data = self.models_by_provider.get(provider)
        if not models_data or not models_data.get("success", False):
            return None
        return models_data

    async def is_valid_model(self, model_id: str) -> bool:
        """Check if a model ID is valid (provider:model format)."""
        provider, model = self.parse_model_id(model_id)
        models = await self.get_models(provider)
        return model in models
        
    async def _refresh_models(self, provider: str) -> None:
        """Refresh models data from the specified provider's API, handling different client methods."""
        client = self.providers.get(provider)
        if not client:
            logger.error(f"Provider '{provider}' client not found during refresh.")
            self.models_by_provider[provider] = {"success": False, "models": [], "error": f"Client for provider '{provider}' not initialized."}
            return

        self._load_from_cache(provider) # Load existing cache first

        result = None
        try:
            if provider == "openai":
                # OpenAI uses client.models.list()
                if hasattr(client, 'client') and client.client: # Check if underlying AsyncOpenAI client exists
                    models_response = await client.client.models.list()
                    # Format the response to match the expected structure
                    result = {
                        "success": True,
                        "models": [{"id": model.id} for model in models_response.data]
                    }
                else:
                    result = {"success": False, "models": [], "error": "OpenAI client not properly initialized."}
            elif hasattr(client, 'get_available_models'):
                # OpenRouter and AI Horde use get_available_models()
                result = await client.get_available_models()
            else:
                result = {"success": False, "models": [], "error": f"Client for provider '{provider}' has no known method to list models."}

        except Exception as e:
            logger.exception(f"Error fetching models from {provider}: {e}")
            result = {"success": False, "models": [], "error": f"Exception fetching models: {str(e)}"}

        # Process the result
        if result and result.get("success"):
            self.models_by_provider[provider] = result
            self.last_update[provider] = datetime.now()
            self._save_to_cache(provider)
            logger.info(f"Successfully refreshed models for provider '{provider}'. Found {len(result.get('models', []))} models.")
        else:
            error_msg = result.get("error", "Unknown error") if result else "Unknown error (result was None)"
            logger.error(f"Failed to refresh models from {provider}: {error_msg}")
            # Keep existing cache if refresh fails, unless there's no cache
            if provider not in self.models_by_provider:
                self.models_by_provider[provider] = {"success": False, "models": [], "error": error_msg}

    def _cache_file(self, provider: str) -> str:
        """Path to a provider's own cache file."""
        return os.path.join(self.data_directory, f"models_cache_{provider}.json")

    def _is_cache_stale(self, provider: str) -> bool:
        """Check if the cached model data for a provider is stale."""
        last_update = self.last_update.get(provider)
        if not last_update:
            return True
        return datetime.now() - last_update > self.cache_duration

    def _load_from_cache(self, provider: str) -> None:
        """Load a provider's models data from its cache file."""
        cache_file = self._cache_file(provider)
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                if cache_data.pop("cache_version", None) != self.CACHE_VERSION:
                    logger.info(f"Discarding outdated models cache for '{provider}'.")
                    return
                if "last_update" in cache_data:
                    self.last_update[provider] = datetime.fromisoformat(cache_data.pop("last_update"))
                self.models_by_provider[provider] = cache_data
        except Exception as e:
            logger.error(f"Error loading models cache: {str(e)}")

    def _save_to_cache(self, provider: str) -> None:
        """Save a provider's models data to its cache file."""
        try:
            cache_data = {**self.models_by_provider.get(provider, {})}
            cache_data["cache_version"] = self.CACHE_VERSION
            cache_data["last_update"] = datetime.now().isoformat()
            with open(self._cache_file(provider), 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Error saving models cache: {str(e)}")

    async def get_models_by_capability(self, capability: str, provider: str = None, force_refresh: bool = False) -> List[str]:
        """Get models that support a specific capability for a given provider."""
        if not provider:
            provider = "openrouter"  # Default to openrouter

        models_data = await self._get_provider_data(provider, force_refresh)
        if not models_data:
            return []

        # Return full provider/model format for consistency
        models = []
        for model in models_data.get("models", []):
            if model.get(f"supports_{capability}", False):
                model_id = model.get("id", "")
                # Ensure provider prefix is included
                if "/" not in model_id:
                    model_id = f"{provider}/{model_id}"
                models.append(model_id)
        return models

    async def get_vision_models(self, provider: str = None, force_refresh: bool = False) -> List[str]:
        """Get models that support vision/image analysis."""
        return await self.get_models_by_capability("vision", provider, force_refresh)
