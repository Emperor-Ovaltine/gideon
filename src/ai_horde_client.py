async def get_available_models(self) -> Dict[str, Any]:
    """Get a list of available models on AI Horde."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.api_key:
                headers["apikey"] = self.api_key
            
            async with session.get(
                f"{self.base_url}/status/models",
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to get models: ({response.status}) {error_text}")
                    return {"error": f"API Error ({response.status}): {error_text}"}
                
                models_data = await response.json()
                
                # Process the models data to extract only image models
                image_models = []
                for model in models_data:
                    if model.get("type") == "image" and not model.get("unavailable", False):
                        image_models.append({
                            "name": model.get("name"),
                            "count": model.get("count", 0),
                            "performance": model.get("performance", "unknown"),
                            "queued": model.get("queued", 0),
                            "description": model.get("description", "")
                        })
                
                return {
                    "success": True,
                    "models": image_models,
                    "raw_data": models_data  # Keep the raw data in case it's needed
                }
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        return {"error": f"Error getting models: {str(e)}"}
