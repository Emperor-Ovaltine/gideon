import json
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger('model_manager')

class ModelManager:
    """Manages model information for the bot."""
    
    def __init__(self, openrouter_client, data_directory: str):
        self.openrouter_client = openrouter_client
        self.cache_file = os.path.join(data_directory, "models_cache.json")
        self.models_data = None
        self.last_update = None
        self.cache_duration = timedelta(hours=12)  # Cache valid for 12 hours
    
    async def get_models(self, force_refresh: bool = False) -> List[str]:
        """Get available models, using cache when possible."""
        # Check if we need to refresh the cache
        if force_refresh or self.models_data is None or self._is_cache_stale():
            await self._refresh_models()
        
        if not self.models_data or not self.models_data.get("success", False):
            return []
            
        return [model["id"] for model in self.models_data.get("models", [])]
    
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
    
    def get_allowed_models(self) -> List[str]:
        """Get list of allowed model IDs."""
        if not self.models_data or not self.models_data.get("success"):
            return []
            
        return [model["id"] for model in self.models_data.get("models", [])]
    
    def is_valid_model(self, model_id: str) -> bool:
        """Check if a model ID is valid."""
        return model_id in self.get_allowed_models()
    
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
