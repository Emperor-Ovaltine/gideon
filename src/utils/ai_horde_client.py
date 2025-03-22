import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger('ai_horde_client')

class AIHordeClient:
    """Client for interacting with AI Horde image generation API."""
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://aihorde.net/api/v2"
        
    async def generate_image(self, 
                           prompt: str, 
                           negative_prompt: str = "",
                           width: int = 512, 
                           height: int = 512,
                           steps: int = 30,
                           model: str = "stable_diffusion_2.1",
                           nsfw: bool = False,
                           max_wait_time: int = 300) -> Dict[str, Any]:
        """
        Generate an image using AI Horde.
        
        Args:
            prompt: Text description of the desired image
            negative_prompt: What the image should not contain
            width: Image width (multiple of 64, max 1024)
            height: Image height (multiple of 64, max 1024)
            steps: Generation steps (higher = more detail but slower)
            model: AI model to use
            nsfw: Whether to allow NSFW content
            max_wait_time: Maximum time to wait for generation in seconds
            
        Returns:
            Dict containing image data or error information
        """
        try:
            # Setup headers - API key is optional but gives better priority
            headers = {
                "Content-Type": "application/json",
            }
            
            if self.api_key:
                headers["apikey"] = self.api_key
            
            # Prepare the generation parameters
            payload = {
                "prompt": prompt,
                "params": {
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "sampler_name": "k_euler_a",
                    "cfg_scale": 7.5,
                },
                "nsfw": nsfw,
                "models": [model],
                "r2": True,  # Use R2 storage for images
            }
            
            async with aiohttp.ClientSession() as session:
                # Step 1: Submit the generation request
                async with session.post(
                    f"{self.base_url}/generate/async",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 202:
                        error_text = await response.text()
                        logger.error(f"Failed to submit generation: ({response.status}) {error_text}")
                        return {"error": f"API Error ({response.status}): {error_text}"}
                    
                    submission = await response.json()
                    request_id = submission.get("id")
                    
                    if not request_id:
                        return {"error": "Failed to get request ID from AI Horde"}
                    
                    logger.info(f"Image generation submitted with ID: {request_id}")
                
                # Step 2: Poll for results
                start_time = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start_time < max_wait_time:
                    async with session.get(
                        f"{self.base_url}/generate/check/{request_id}",
                        headers=headers
                    ) as check_response:
                        status = await check_response.json()
                        
                        # Check if generation failed
                        if "faulted" in status and status["faulted"]:
                            return {"error": "Generation failed on AI Horde"}
                        
                        # Check if generation is done
                        if "done" in status and status["done"]:
                            break
                        
                        # If not done, wait and continue polling
                        wait_time = min(5, max(1, status.get("wait_time", 2)))
                        logger.debug(f"Waiting for image, estimated time: {status.get('wait_time', '?')}s")
                        await asyncio.sleep(wait_time)
                
                # Check if we timed out
                if asyncio.get_event_loop().time() - start_time >= max_wait_time:
                    return {"error": f"Generation timed out after {max_wait_time} seconds"}
                
                # Step 3: Retrieve the results
                async with session.get(
                    f"{self.base_url}/generate/status/{request_id}",
                    headers=headers
                ) as status_response:
                    result = await status_response.json()
                    
                    # Process and return the image data
                    if "generations" in result and result["generations"]:
                        generation = result["generations"][0]
                        return {
                            "success": True,
                            "image_url": generation.get("img"),
                            "model": generation.get("model"),
                            "seed": generation.get("seed"),
                        }
                    else:
                        return {"error": "No image was generated"}
                        
        except Exception as e:
            logger.error(f"Error generating image: {str(e)}")
            return {"error": f"Error generating image: {str(e)}"}

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
                    
                    return await response.json()
        except Exception as e:
            logger.error(f"Error getting models: {str(e)}")
            return {"error": f"Error getting models: {str(e)}"}