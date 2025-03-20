import aiohttp
import json
import asyncio
import socket
import logging
import base64
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('openrouter_client')

class OpenRouterClient:
    def __init__(self, api_key, system_prompt=None, default_model="google/gemini-2.0-flash-exp:free"):
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.model = default_model
        # Updated to ensure correct API endpoint
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        # Alternative endpoints to try if the main one fails
        self.alternative_urls = [
            "https://api.openrouter.ai/api/v1/chat/completions",
            "https://api.openrouter.ai/v1/chat/completions"
        ]
        # Define which models support image inputs
        self.vision_models = [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-exp:free",
            "anthropic/claude-3.7-sonnet",
            "anthropic/claude-3-opus",
            "anthropic/claude-3-sonnet"
        ]
        
    def model_supports_vision(self):
        """Check if the current model supports image inputs"""
        return any(vm in self.model for vm in self.vision_models)
        
    async def verify_dns_resolution(self, hostname):
        """Verify if the hostname can be resolved via DNS"""
        try:
            # Try to resolve the hostname
            info = await asyncio.get_event_loop().getaddrinfo(
                hostname, None, family=socket.AF_INET
            )
            logger.info(f"Successfully resolved {hostname}: {info[0][4][0]}")
            return True
        except socket.gaierror as e:
            logger.error(f"Failed to resolve {hostname}: {e}")
            return False

    async def send_message(self, message, max_retries=3):
        """Legacy method for backward compatibility"""
        return await self.send_message_with_history([{"role": "user", "content": message}], max_retries)

    async def encode_image_to_base64(self, image_data):
        """Encode image data to base64 string"""
        try:
            # image_data should be bytes from the attachment
            encoded = base64.b64encode(image_data).decode('utf-8')
            return encoded
        except Exception as e:
            logger.error(f"Error encoding image: {str(e)}")
            return None

    async def send_message_with_history(self, message_history, max_retries=3, images=None):
        """
        Send message with conversation history and optional images
        
        Args:
            message_history: List of message objects (role, content)
            max_retries: Number of retry attempts
            images: List of {'data': binary_data, 'type': 'mime/type'} dictionaries
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://discord-bot"  # OpenRouter requires a referer
        }
        
        # Create messages array with system prompt if available
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        
        # Process the rest of the messages
        if images and len(images) > 0 and self.model_supports_vision():
            # For the last user message, we'll add the images
            processed_messages = []
            for i, msg in enumerate(message_history):
                # Only process user messages that might need images
                if i == len(message_history) - 1 and msg["role"] == "user" and images:
                    # Format with content parts for multimodal
                    content_parts = [
                        {"type": "text", "text": msg["content"]}
                    ]
                    
                    # Add images to content parts
                    for img in images:
                        if "data" in img and "type" in img:
                            # Convert image data to base64
                            b64_image = await self.encode_image_to_base64(img["data"])
                            if b64_image:
                                content_parts.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{img['type']};base64,{b64_image}"
                                    }
                                })
                    
                    # Add the message with multiple content parts
                    processed_messages.append({
                        "role": "user",
                        "content": content_parts
                    })
                else:
                    # Add regular messages as they are
                    processed_messages.append(msg)
            
            # Use processed messages
            messages.extend(processed_messages)
        else:
            # No images or model doesn't support vision
            messages.extend(message_history)
        
        payload = {
            "model": self.model,  # Use the selected model
            "messages": messages
        }

        # Extract hostname for DNS check
        from urllib.parse import urlparse
        parsed_url = urlparse(self.base_url)
        hostname = parsed_url.netloc
        
        # Check DNS resolution
        if not await self.verify_dns_resolution(hostname):
            return f"DNS resolution failed for {hostname}. Please check your internet connection or DNS settings."

        # Try the main URL first, then fall back to alternatives
        urls_to_try = [self.base_url] + self.alternative_urls
        
        for url in urls_to_try:
            for attempt in range(max_retries):
                try:
                    logger.info(f"Attempting to connect to {url} (Attempt {attempt+1}/{max_retries})")
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=payload, headers=headers, timeout=30) as response:
                            if response.status == 200:
                                data = await response.json()
                                return data['choices'][0]['message']['content']
                            elif response.status == 429:
                                retry_after = int(response.headers.get('retry-after', 5))
                                logger.warning(f"Rate limited. Retrying after {retry_after} seconds")
                                await asyncio.sleep(retry_after)
                                continue
                            else:
                                error_text = await response.text()
                                logger.error(f"API error: {response.status}, {error_text}")
                                if attempt == max_retries - 1 and url == urls_to_try[-1]:
                                    return f"Error: {response.status}, {error_text}"
                except aiohttp.ClientError as e:
                    logger.error(f"Client error on {url}: {str(e)}")
                    if attempt == max_retries - 1 and url == urls_to_try[-1]:
                        return f"Client error: {str(e)}"
                except aiohttp.ServerTimeoutError:
                    logger.error(f"Timeout error on {url}")
                    if attempt == max_retries - 1 and url == urls_to_try[-1]:
                        return "Error: Request timed out"
                except Exception as e:
                    logger.error(f"Unexpected error on {url}: {str(e)}")
                    if attempt == max_retries - 1 and url == urls_to_try[-1]:
                        return f"Unexpected error: {str(e)}"
                
                # If we're here, the attempt failed, so wait before retrying
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return "Failed to connect to OpenRouter API after multiple attempts"

    def estimate_tokens(self, text):
        """Rough estimate of tokens (4 chars ≈ 1 token)"""
        return len(text) // 4

    async def get_response(self, message):
        response = await self.send_message(message)
        return response if response else "Error: Unable to get response"