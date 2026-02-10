"""Client for interacting with OpenRouter API for image generation."""
import aiohttp
import base64
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger('openrouter_image_client')


class OpenRouterImageClient:
    """Client for generating images using OpenRouter API.

    OpenRouter provides access to various image generation models through a unified API.
    This client uses the /chat/completions endpoint with modalities=["image", "text"]
    to generate images from text prompts.

    Supported models include Google Gemini variants and other models with 'image'
    in their output_modalities.
    """

    def __init__(self, api_key: str):
        """
        Initialize OpenRouter Image client.

        Args:
            api_key: OpenRouter API key
        """
        if not api_key:
            logger.warning("OpenRouter API key is not configured. Image generation will not work.")
            self.client = None
        else:
            self.api_key = api_key
            self.base_url = "https://openrouter.ai/api/v1"
            self.client = True  # Flag to track if client is initialized
            logger.info("OpenRouter Image client initialized successfully.")

    async def generate_image(self,
                            prompt: str,
                            negative_prompt: str = "",
                            width: int = 1024,
                            height: int = 1024,
                            steps: int = 20,
                            model: Optional[str] = None,
                            **kwargs) -> Dict[str, Any]:
        """
        Generate an image using OpenRouter API.

        Args:
            prompt: Text description of the desired image
            negative_prompt: What to exclude (appended to prompt for models that support it)
            width: Image width (not used by OpenRouter, kept for signature compatibility)
            height: Image height (not used by OpenRouter, kept for signature compatibility)
            steps: Generation steps (not used by OpenRouter, kept for signature compatibility)
            model: OpenRouter model ID (e.g., "google/gemini-2.0-flash-exp")
            **kwargs: Additional parameters:
                - aspect_ratio: OpenRouter aspect ratio ("1:1", "16:9", "9:16", "4:3", "3:4")
                - image_size: OpenRouter image size ("1K", "2K", "4K")

        Returns:
            Dict containing:
                - success: True if generation succeeded
                - image_data: bytes of the PNG image (decoded from base64)
                - image_url: URL if returned instead of base64
                - model_used: The model that generated the image
            Or on failure:
                - success: False
                - error: Error message
        """
        if not self.client:
            return {
                "success": False,
                "error": "OpenRouter client is not initialized (API key missing or invalid)."
            }

        # Model is required for OpenRouter - no default
        if not model:
            return {
                "success": False,
                "error": "No model specified. OpenRouter requires an explicit model selection."
            }

        try:
            # Build the API request headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/eoko-dev/gideon",
                "X-Title": "Gideon Discord Bot"
            }

            # Prepare the message content
            # OpenRouter image generation uses chat completion format with modalities parameter
            message_content = prompt

            # Add negative prompt to the message if provided
            # Note: This is model-dependent - some models may not honor it
            if negative_prompt:
                message_content += f"\n\nNegative prompt (avoid these elements): {negative_prompt}"

            messages = [
                {
                    "role": "user",
                    "content": message_content
                }
            ]

            # Build the payload
            # Modalities can be overridden via kwargs (from dashboard config)
            # Default: ["image", "text"] which works with most image-capable models
            modalities = kwargs.get("modalities", ["image", "text"])

            payload = {
                "model": model,
                "messages": messages,
                "modalities": modalities,
            }

            # Add OpenRouter-specific parameters if provided
            # These work primarily with Gemini models
            if "aspect_ratio" in kwargs and kwargs["aspect_ratio"]:
                payload["aspect_ratio"] = kwargs["aspect_ratio"]

            if "image_size" in kwargs and kwargs["image_size"]:
                payload["image_size"] = kwargs["image_size"]

            logger.info(f"Requesting OpenRouter image generation with model: {model}")
            logger.debug(f"Payload: {json.dumps(payload, default=str)}")

            # Make the API request
            timeout = aiohttp.ClientTimeout(total=120)  # 2 minutes timeout for image generation
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API Error ({response.status}): {error_text}")

                        # Parse common errors for better user feedback
                        if response.status == 401:
                            return {"success": False, "error": "Invalid API key"}
                        elif response.status == 400:
                            # Try to extract error message from JSON
                            try:
                                error_json = json.loads(error_text)
                                error_msg = error_json.get("error", {}).get("message", error_text)
                                return {"success": False, "error": f"Bad Request: {error_msg}"}
                            except json.JSONDecodeError:
                                return {"success": False, "error": f"Bad Request: {error_text}"}
                        elif response.status == 429:
                            return {"success": False, "error": "Rate limit exceeded. Please try again later."}
                        elif response.status == 402:
                            return {"success": False, "error": "Insufficient credits. Please add credits to your OpenRouter account."}
                        else:
                            return {"success": False, "error": f"API Error ({response.status}): {error_text[:200]}"}

                    # Parse the response
                    result = await response.json()
                    logger.debug(f"OpenRouter response keys: {result.keys()}")

                    # Extract the image from the response
                    # OpenRouter returns images in message.images array as base64 data URLs
                    if "choices" not in result or len(result["choices"]) == 0:
                        return {"success": False, "error": "No response from OpenRouter API"}

                    choice = result["choices"][0]
                    message = choice.get("message", {})

                    # Check for images in the response
                    images = message.get("images", [])
                    if not images or len(images) == 0:
                        # Model may not support image generation
                        # Check if there's text content to provide context
                        text_content = message.get("content", "")
                        if text_content:
                            logger.warning(f"Model returned text instead of image: {text_content[:100]}")
                        return {
                            "success": False,
                            "error": f"Model '{model}' did not return an image. It may not support image generation."
                        }

                    # Get the first image
                    image_item = images[0]
                    logger.debug(f"Image item type: {type(image_item)}, content: {str(image_item)[:200]}")

                    # Handle different response formats from OpenRouter
                    # Format 1: Direct data URL string
                    # Format 2: Object with nested image_url.url structure: {"image_url": {"url": "data:..."}}
                    # Format 3: Object with direct url: {"url": "data:..."}
                    image_data_url = None

                    if isinstance(image_item, str):
                        image_data_url = image_item
                    elif isinstance(image_item, dict):
                        # Check for nested structure: {"image_url": {"url": "..."}}
                        image_url_field = image_item.get("image_url")
                        if isinstance(image_url_field, dict):
                            image_data_url = image_url_field.get("url", "")
                        elif isinstance(image_url_field, str):
                            image_data_url = image_url_field
                        else:
                            # Fallback to direct url field
                            image_data_url = image_item.get("url", "")
                    else:
                        return {"success": False, "error": f"Unexpected image format: {type(image_item)}"}

                    if not image_data_url:
                        return {"success": False, "error": f"Empty image data in response. Item: {str(image_item)[:200]}"}

                    # Check if it's a URL or base64 data URL
                    if not image_data_url.startswith("data:"):
                        # It's a direct URL - return it as image_url
                        logger.info(f"OpenRouter returned image URL directly")
                        return {
                            "success": True,
                            "image_url": image_data_url,
                            "model_used": model
                        }

                    # Parse data URL: data:image/png;base64,<base64data>
                    try:
                        # Split on comma to separate metadata from data
                        if "," not in image_data_url:
                            return {"success": False, "error": "Invalid image data URL format"}

                        header, base64_data = image_data_url.split(",", 1)

                        # Decode base64 to bytes
                        image_bytes = base64.b64decode(base64_data)

                        logger.info(f"Successfully decoded image: {len(image_bytes)} bytes")

                        return {
                            "success": True,
                            "image_data": image_bytes,
                            "model_used": model
                            # OpenRouter doesn't return seed in responses
                        }

                    except Exception as decode_error:
                        logger.error(f"Failed to decode base64 image: {decode_error}")
                        return {
                            "success": False,
                            "error": f"Failed to decode image data: {str(decode_error)}"
                        }

        except aiohttp.ClientError as e:
            logger.error(f"Network error during OpenRouter image generation: {e}")
            return {"success": False, "error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.exception(f"Unexpected error during OpenRouter image generation: {e}")
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    async def get_image_models(self) -> Dict[str, Any]:
        """
        Get a list of OpenRouter models that support image generation.

        Returns:
            Dict with "success": True and "models" list, or "success": False with "error"
        """
        if not self.client:
            return {"success": False, "error": "Client not initialized"}

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/eoko-dev/gideon",
                "X-Title": "Gideon Discord Bot"
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/models",
                    headers=headers
                ) as response:
                    if response.status != 200:
                        return {"success": False, "error": "Failed to fetch model list"}

                    models_data = await response.json()

                    # Filter to only models with image generation capability
                    image_models = []
                    total_models = len(models_data.get("data", []))
                    logger.debug(f"Processing {total_models} total models from OpenRouter")

                    # Debug: Log structure of first model to understand API response
                    if total_models > 0:
                        sample = models_data.get("data", [])[0]
                        arch = sample.get("architecture", {})
                        logger.info(f"Sample model keys: {list(sample.keys())}")
                        logger.info(f"Sample architecture.output_modalities: {arch.get('output_modalities')}")
                        logger.info(f"Sample architecture.modality: {arch.get('modality')}")

                    for model_info in models_data.get("data", []):
                        model_id = model_info.get("id")
                        # output_modalities and modality are nested inside architecture
                        architecture = model_info.get("architecture", {}) or {}
                        output_modalities = architecture.get("output_modalities", [])
                        modality_str = architecture.get("modality", "")

                        supports_images = False

                        # Method 1: Direct output_modalities array check
                        if output_modalities and "image" in output_modalities:
                            supports_images = True
                            logger.debug(f"Model {model_id}: found via output_modalities")

                        # Method 2: Parse modality string (e.g., "text+image->text+image")
                        # Check if the OUTPUT part (after ->) contains "image"
                        elif modality_str and "->" in modality_str:
                            output_part = modality_str.split("->")[-1]
                            if "image" in output_part.lower():
                                supports_images = True
                                logger.debug(f"Model {model_id}: found via modality string '{modality_str}'")

                        # Method 3: Check against known image model IDs
                        # OpenRouter API doesn't reliably expose image capability, so we maintain a list
                        # of confirmed image-generation models from https://openrouter.ai/models?output_modalities=image
                        elif model_id:
                            known_image_models = {
                                "sourceful/riverflow-v2-pro",
                                "sourceful/riverflow-v2-fast",
                                "black-forest-labs/flux.2-klein-4b",
                                "bytedance-seed/seedream-4.5",
                                "black-forest-labs/flux.2-max",
                                "sourceful/riverflow-v2-max-preview",
                                "sourceful/riverflow-v2-standard-preview",
                                "sourceful/riverflow-v2-fast-preview",
                                "black-forest-labs/flux.2-flex",
                                "black-forest-labs/flux.2-pro",
                                "google/gemini-3-pro-image-preview",
                                "openai/gpt-5-image-mini",
                                "openai/gpt-5-image",
                                "google/gemini-2.5-flash-image",
                                "google/gemini-2.5-flash-image-preview",
                            }
                            if model_id in known_image_models:
                                supports_images = True
                                logger.debug(f"Model {model_id}: found via known model list")

                        if supports_images:
                            image_models.append({
                                "id": model_id,
                                "name": model_info.get("name", model_id),
                                "output_modalities": output_modalities,
                                "modality": modality_str
                            })

                    logger.info(f"Found {len(image_models)} image-capable models out of {total_models} total models on OpenRouter")
                    return {
                        "success": True,
                        "models": image_models
                    }

        except Exception as e:
            logger.error(f"Error fetching image models: {e}")
            return {"success": False, "error": str(e)}
