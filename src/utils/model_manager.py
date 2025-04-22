import json
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger('model_manager')

class ProviderManager:
    """Manages multiple AI providers and their models."""
    
    def __init__(self, openrouter_client, openai_client, ai_horde_client, data_directory: str):
        self.providers = {
            "openrouter": openrouter_client,
            "openai": openai_client,
            # "ai_horde": ai_horde_client
        }
        self.cache_file = os.path.join(data_directory, "models_cache.json")
        self.models_data = None
        self.last_update = None
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
        
    def __init__(self, openrouter_client, openai_client, ai_horde_client, data_directory: str):
        self.providers = {
            "openrouter": openrouter_client,
            "openai": openai_client,
            "ai_horde": ai_horde_client
        }
        self.cache_file = os.path.join(data_directory, "models_cache.json")
        self.models_data = None
        self.last_update = None
        self.current_provider = None  # Track current provider
        self.cache_duration = timedelta(hours=12)

    async def get_models(self, provider: str, force_refresh: bool = False) -> List[str]:
        """Get available models for a specific provider."""
        logger.debug(f"get_models called for provider: '{provider}' (force_refresh={force_refresh})") # Add logging
        client = self.providers.get(provider)
        if not client:
            logger.error(f"Client lookup failed for provider: '{provider}'") # Add logging
            raise ValueError(f"Provider '{provider}' not found")

        # Clear cache if provider changed
        if self.current_provider and self.current_provider != provider:
            self.models_data = None
            force_refresh = True
            
        self.current_provider = provider
            
        if force_refresh or self.models_data is None or self._is_cache_stale():
            await self._refresh_models(provider)
            
        if not self.models_data or not self.models_data.get("success", False):
            return []
            
        return [model["id"] for model in self.models_data.get("models", []) if "id" in model]

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
            self.models_data = {"success": False, "models": [], "error": f"Client for provider '{provider}' not initialized."}
            return

        self._load_from_cache() # Load existing cache first

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
            self.models_data = result
            self.last_update = datetime.now()
            self._save_to_cache()
            logger.info(f"Successfully refreshed models for provider '{provider}'. Found {len(result.get('models', []))} models.")
        else:
            error_msg = result.get("error", "Unknown error") if result else "Unknown error (result was None)"
            logger.error(f"Failed to refresh models from {provider}: {error_msg}")
            # Keep existing cache if refresh fails, unless there's no cache
            if not self.models_data:
                self.models_data = {"success": False, "models": [], "error": error_msg}

    def _is_cache_stale(self) -> bool:
        """Check if the cached model data is stale."""
        if not self.last_update:
            return True
        return datetime.now() - self.last_update > self.cache_duration
        
    def _load_from_cache(self) -> None:
        """Load models data from cache file."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    if "last_update" in cache_data:
                        self.last_update = datetime.fromisoformat(cache_data["last_update"])
                        del cache_data["last_update"]
                    self.models_data = cache_data
        except Exception as e:
            logger.error(f"Error loading models cache: {str(e)}")
            
    def _save_to_cache(self) -> None:
        """Save models data to cache file."""
        try:
            cache_data = {**self.models_data}
            cache_data["last_update"] = datetime.now().isoformat()
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Error saving models cache: {str(e)}")

class ModelManager(ProviderManager):
    """Maintains backward compatibility with existing code."""
    def __init__(self, openrouter_client, data_directory: str):
        super().__init__(openrouter_client, None, None, data_directory)
        self.openrouter_client = openrouter_client  # Maintain direct reference for backward compatibility
    
    async def get_models(self, force_refresh: bool = False) -> List[str]:
        """Get available model IDs, using cache when possible."""
        # Check if we need to refresh the cache
        if force_refresh or self.models_data is None or self._is_cache_stale():
            await self._refresh_models()
        
        if not self.models_data or not self.models_data.get("success", False):
            logger.warning("Failed to get models or no models data available.")
            return []
            
        return [model["id"] for model in self.models_data.get("models", []) if "id" in model]
    
    def _is_cache_stale(self) -> bool:
        """Check if the cached model data is stale."""
        if not self.last_update:
            return True
        
        return datetime.now() - self.last_update > self.cache_duration
    
    async def _refresh_models(self) -> None:
        """Refresh models data from the API."""
        # First try to load from cache if available
        self._load_from_cache()
        
        # Then try to get fresh data from API
        result = await self.openrouter_client.get_available_models()
        
        if result.get("success"):
            self.models_data = result
            self.last_update = datetime.now()
            # Save to cache
            self._save_to_cache()
        else:
            logger.error(f"Failed to refresh models: {result.get('error', 'Unknown error')}")
            # If we don't have any cached data, set an empty result
            if not self.models_data:
                self.models_data = {"success": False, "models": [], "error": result.get("error")}
    
    def _load_from_cache(self) -> None:
        """Load models data from cache file."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    
                    # Convert cached timestamp to datetime
                    if "last_update" in cache_data:
                        self.last_update = datetime.fromisoformat(cache_data["last_update"])
                        # Remove last_update from data
                        del cache_data["last_update"]
                    
                    self.models_data = cache_data
                    logger.info(f"Loaded {len(self.models_data.get('models', []))} models from cache")
        except Exception as e:
            logger.error(f"Error loading models cache: {str(e)}")
    
    def _save_to_cache(self) -> None:
        """Save models data to cache file."""
        try:
            # Create a copy of the data to avoid modifying original
            cache_data = {**self.models_data}
            
            # Add timestamp
            cache_data["last_update"] = datetime.now().isoformat()
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
                
            logger.info(f"Saved {len(self.models_data.get('models', []))} models to cache")
        except Exception as e:
            logger.error(f"Error saving models cache: {str(e)}")
    
    # REMOVED this method as get_models serves the purpose now
    # def get_allowed_models(self) -> List[str]:
    #     """Get list of allowed model IDs."""
    #     if not self.models_data or not self.models_data.get("success"):
    #         return []
            
    #     return [model["id"] for model in self.models_data.get("models", [])]
    
    # UPDATED: Make async and ensure data is potentially refreshed
    async def is_valid_model(self, model_id: str) -> bool:
        """Check if a model ID is valid by checking against the fetched list."""
        # Ensure the model list is reasonably fresh before checking
        # get_models handles the refresh logic if needed (based on cache expiry)
        available_models = await self.get_models() 
        is_valid = model_id in available_models
        if not is_valid:
             logger.warning(f"Model '{model_id}' not found in available models.")
        return is_valid
    
    def update_vision_models(self) -> None:
        """Update the vision models list in the OpenRouter client."""
        if not self.models_data or not self.models_data.get("success"):
            return
            
        vision_models = []
        for model in self.models_data.get("models", []):
            if model.get("supports_vision"):
                # Extract the model family name
                model_id = model.get("id", "")
                if "/" in model_id:
                    model_family = model_id.split("/")[1]
                    if model_family not in vision_models:
                        vision_models.append(model_family)
        
        # Update the client's vision models
        self.openrouter_client.vision_models = vision_models
        logger.info(f"Updated vision models list: {vision_models}")

    async def get_models_by_capability(self, capability: str, force_refresh: bool = False) -> List[str]:
        """Get models that support a specific capability."""
        if force_refresh or self.models_data is None or self._is_cache_stale():
            await self._refresh_models()
        if not self.models_data or not self.models_data.get("success", False):
            return []
        return [model["id"] for model in self.models_data.get("models", []) 
                if model.get(f"supports_{capability}", False)]

    async def get_vision_models(self, force_refresh: bool = False) -> List[str]:
        """Get models that support vision/image analysis."""
        return await self.get_models_by_capability("vision", force_refresh)

    async def get_model_info(self, model_id: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get detailed info for a specific model."""
        if force_refresh or self.models_data is None or self._is_cache_stale():
            await self._refresh_models()
        if not self.models_data or not self.models_data.get("success", False):
            return None
        for model in self.models_data.get("models", []):
            if model.get("id") == model_id:
                return model
        return None

async def get_model_choices(client):
    """Get model choices in a consistent format from either client."""
    models_data = await client.get_available_models()
    
    if "error" in models_data:
        return []
        
    if "models" in models_data and isinstance(models_data["models"], list):
        models_list = models_data["models"]
        # Handle different field names (OpenRouter uses "id", AI Horde uses "name")
        return [model.get("id") or model.get("name") for model in models_list if model.get("id") or model.get("name")]
    
    # Direct format (some versions of AI Horde client)
    if isinstance(models_data, list):
        return [model.get("name") for model in models_data if model.get("name")]
    
    return []
