import logging
import asyncio
from openai import AsyncOpenAI, OpenAIError

logger = logging.getLogger('openai_client')

class OpenAIClient:
    """Client for interacting with the OpenAI API, specifically for image generation."""

    def __init__(self, api_key: str):
        """
        Initializes the OpenAI client.

        Args:
            api_key: The OpenAI API key.
        """
        if not api_key:
            logger.warning("OpenAI API key is not configured. Image generation will not work.")
            self.client = None
        else:
            try:
                # Use AsyncOpenAI for compatibility with discord.py's async nature
                self.client = AsyncOpenAI(api_key=api_key)
                logger.info("OpenAI client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.client = None

    async def generate_image(self, prompt: str, model: str, size: str, quality: str = None, style: str = None) -> dict:
        """
        Generates an image using the OpenAI API (Dall-E 2 or Dall-E 3).

        Args:
            prompt: The text prompt describing the image.
            model: The model to use ('dall-e-2' or 'dall-e-3').
            size: The desired size ('1024x1024', '1792x1024', '1024x1792' for D3; '1024x1024', '512x512', '256x256' for D2).
                  Note: The unified command will likely enforce '1024x1024'.
            quality: The quality ('standard' or 'hd'). Only applicable for 'dall-e-3'.
            style: The style ('vivid' or 'natural'). Only applicable for 'dall-e-3'.

        Returns:
            A dictionary containing either the image URL on success or an error message on failure.
            Example success: {"success": True, "image_url": "...", "model_used": "dall-e-3", "revised_prompt": "..."}
            Example failure: {"success": False, "error": "API key invalid."}
        """
        if not self.client:
            return {"success": False, "error": "OpenAI client is not initialized (API key missing or invalid)."}

        params = {
            "prompt": prompt,
            "model": model,
            "size": size,
            "n": 1,
            "response_format": "url",
        }

        # Add quality and style only if model is dall-e-3 and they are provided
        if model == "dall-e-3":
            if quality:
                params["quality"] = quality
            if style:
                params["style"] = style
        elif quality or style:
             logger.warning(f"Quality/Style parameters provided for non-Dall-E 3 model ({model}). Ignoring.")


        logger.info(f"Requesting OpenAI image generation with params: {params}")

        try:
            response = await self.client.images.generate(**params)

            if response.data and len(response.data) > 0:
                image_data = response.data[0]
                result = {
                    "success": True,
                    "image_url": image_data.url,
                    "model_used": model, # Return the requested model
                    "revised_prompt": getattr(image_data, 'revised_prompt', None) # DALL-E 3 might revise prompts
                }
                logger.info(f"OpenAI image generated successfully: {image_data.url}")
                return result
            else:
                logger.error("OpenAI API returned success but no image data.")
                return {"success": False, "error": "API returned success but no image data found."}

        except OpenAIError as e:
            logger.error(f"OpenAI API error during image generation: {e}")
            # Try to provide a more specific error message if available
            error_message = str(e)
            if hasattr(e, 'message'):
                error_message = e.message
            elif hasattr(e, 'body') and e.body and 'message' in e.body:
                 error_message = e.body['message']

            return {"success": False, "error": f"OpenAI API Error: {error_message}"}
        except Exception as e:
            logger.exception(f"Unexpected error during OpenAI image generation: {e}")
            return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

# Example usage (for testing purposes)
async def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("Set the OPENAI_API_KEY environment variable to run this test.")
        return

    logging.basicConfig(level=logging.INFO)
    client = OpenAIClient(api_key)

    # Test DALL-E 3
    print("\nTesting DALL-E 3...")
    result_d3 = await client.generate_image(
        prompt="A photorealistic image of an astronaut riding a horse on the moon",
        model="dall-e-3",
        size="1024x1024",
        quality="standard",
        style="vivid"
    )
    print(f"DALL-E 3 Result: {result_d3}")

    # Test DALL-E 2
    print("\nTesting DALL-E 2...")
    result_d2 = await client.generate_image(
        prompt="A cute cat wearing a small hat",
        model="dall-e-2",
        size="1024x1024" # DALL-E 2 supports this size
    )
    print(f"DALL-E 2 Result: {result_d2}")

    # Test Error Handling (e.g., invalid model)
    # print("\nTesting Error Handling (Invalid Model)...")
    # result_err = await client.generate_image(
    #     prompt="Test prompt",
    #     model="invalid-model",
    #     size="1024x1024"
    # )
    # print(f"Error Result: {result_err}")

if __name__ == "__main__":
    # Requires OPENAI_API_KEY to be set in environment for testing
    # asyncio.run(main())
    pass # Keep __main__ block but don't run by default