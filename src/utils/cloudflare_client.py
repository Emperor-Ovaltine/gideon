"""Client for interacting with Cloudflare Worker image generation API."""
import aiohttp
import logging
import json
import os
import tempfile
import uuid
from typing import Dict, Any, Optional

logger = logging.getLogger('cloudflare_client')

class CloudflareWorkerClient:
    """Client for generating images using Cloudflare Worker API."""
    
    def __init__(self, api_url: str, api_key: Optional[str] = None):
        self.api_url = api_url
        self.api_key = api_key
    
    async def test_connection(self, simple_prompt: str = "test") -> Dict[str, Any]:
        """Test connection with minimal payload matching the working curl command."""
        try:
            # Use the exact format that works with curl
            simple_payload = {"prompt": simple_prompt}
            
            logger.info(f"Testing connection to {self.api_url} with simplified payload")
            
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=simple_payload,
                    timeout=30  # Shorter timeout for test
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Test failed: {response.status} - {error_text}")
                        return {"success": False, "error": f"HTTP {response.status}: {error_text}"}
                    
                    # Try to determine if response is JSON or binary image
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        result = await response.json()
                        return {"success": True, "result_type": "json", "data": result}
                    elif "image/" in content_type:
                        # It's returning image data directly
                        image_data = await response.read()
                        return {"success": True, "result_type": "binary_image", "size": len(image_data)}
                    else:
                        text = await response.text()
                        return {"success": True, "result_type": "unknown", "content_type": content_type, "preview": text[:100]}
                        
        except Exception as e:
            logger.error(f"Connection test error: {str(e)}")
            return {"success": False, "error": str(e)}
        
    async def generate_image(self, 
                          prompt: str,
                          negative_prompt: str = "",
                          width: int = 768,
                          height: int = 768,
                          steps: int = 25,
                          seed: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate an image using the Cloudflare Worker API with flux1 schnell model.
        
        Args:
            prompt: Text description of the desired image
            negative_prompt: What the image should not contain
            width: Image width (recommended: 768 or 512)
            height: Image height (recommended: 768 or 512)
            steps: Generation steps (higher = more detail but slower)
            seed: Random seed for reproducibility (optional)
            
        Returns:
            Dict containing image data or error information
        """
        try:
            # Setup headers
            headers = {
                "Content-Type": "application/json",
            }
            
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Try simpler payload format first - like the working curl example
            simple_payload = {"prompt": prompt}
            
            # Full payload with all parameters (if the worker API accepts them)
            full_payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "model": "flux1_schnell"
            }
            
            # Add seed if provided
            if seed is not None:
                full_payload["seed"] = seed
            
            # Choose which payload to use - try the simple one first
            payload = simple_payload
            
            logger.info(f"Sending image generation request to {self.api_url}")
            logger.debug(f"Payload: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=120  # Longer timeout for image generation
                ) as response:
                    status = response.status
                    content_type = response.headers.get("Content-Type", "")
                    
                    logger.info(f"Received response: HTTP {status}, Content-Type: {content_type}")
                    
                    if status != 200:
                        error_text = await response.text()
                        logger.error(f"Cloudflare Worker API Error ({status}): {error_text}")
                        return {"error": f"API Error ({status}): {error_text}"}
                    
                    # Handle different response types
                    if "application/json" in content_type:
                        # JSON response with image URL
                        result = await response.json()
                        if "image_url" in result:
                            return {
                                "success": True,
                                "image_url": result["image_url"],
                                "seed": result.get("seed", seed),
                                "model": "flux1_schnell"
                            }
                        else:
                            return {"error": "No image URL in response", "raw_response": result}
                    elif "image/" in content_type:
                        # Direct binary image response
                        # Save to temp file and return local URL
                        image_data = await response.read()
                        if not image_data:
                            return {"error": "Empty image response"}
                        
                        # Create temp directory if needed
                        temp_dir = os.path.join(tempfile.gettempdir(), "gideon_images")
                        os.makedirs(temp_dir, exist_ok=True)
                        
                        # Save image to file
                        filename = f"image_{uuid.uuid4()}.jpg"
                        filepath = os.path.join(temp_dir, filename)
                        with open(filepath, "wb") as f:
                            f.write(image_data)
                        
                        # Discord can't directly show local files, so this is for debugging only
                        return {
                            "success": True,
                            "image_data": image_data,
                            "local_path": filepath,
                            "seed": seed,
                            "model": "flux1_schnell",
                            "content_type": content_type
                        }
                    else:
                        return {"error": f"Unexpected content type: {content_type}"}
                        
        except aiohttp.ClientError as e:
            logger.error(f"Network error when generating image: {str(e)}")
            return {"error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"Error generating image: {str(e)}")
            return {"error": f"Error generating image: {str(e)}"}
