import aiohttp
import json
import asyncio
import socket
import logging
import base64
from io import BytesIO
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('openrouter_client')

class OpenRouterClient:
    """Client for interacting with the OpenRouter API."""
    
    def __init__(self, api_key: str, system_prompt: str, default_model: str):
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.model = default_model
        self.base_url = "https://openrouter.ai/api/v1"
        
        # List of model name fragments that support vision
        self.vision_models = [
            "claude-3", 
            "gpt-4-vision", 
            "gpt-4-turbo",
            "gemini"
        ]
        
    def model_supports_vision(self) -> bool:
        """Check if the current model supports vision/images."""
        return any(vision_model in self.model.lower() for vision_model in self.vision_models)
    
    async def verify_dns_resolution(self, domain: str) -> bool:
        """Verify that we can resolve the DNS for the given domain."""
        try:
            await asyncio.get_event_loop().getaddrinfo(domain, 443)
            return True
        except socket.gaierror:
            return False
            
    async def send_message_with_history(
        self, 
        messages: List[Dict[str, str]],
        images: List[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None
    ) -> str:
        """Send a message with conversation history to the AI model."""
        # Use provided system prompt or fall back to default
        prompt_to_use = system_prompt if system_prompt is not None else self.system_prompt
        
        # Use provided model or fall back to the default
        model_to_use = model if model is not None else self.model
        
        # Add logging
        logger.info(f"Using model: {model_to_use}")
        logger.info(f"System prompt length: {len(prompt_to_use)}")
        
        # Prepare the full conversation context with system prompt
        conversation = [{"role": "system", "content": prompt_to_use}]
        
        # Add the message history
        conversation.extend(messages)
        
        # If we have images and the model supports them, format them correctly
        if images and self.model_supports_vision():
            # Find the last user message to add images to
            for i in range(len(conversation) - 1, -1, -1):
                if conversation[i]["role"] == "user":
                    # We need to convert the message to the proper format for images
                    user_message = conversation[i]["content"]
                    
                    # Format differs between models
                    if "claude" in self.model.lower():
                        # Claude format - XML tags
                        image_tags = []
                        for img in images:
                            base64_image = base64.b64encode(img['data']).decode('utf-8')
                            mime_type = img['type']
                            image_tags.append(f'<image format="{mime_type}" base64="{base64_image}" />')
                        
                        # Combine text and images
                        conversation[i]["content"] = "\n".join(image_tags) + "\n\n" + user_message
                    else:
                        # GPT-4 Vision and similar formats - content array
                        content_array = [{"type": "text", "text": user_message}]
                        
                        for img in images:
                            base64_image = base64.b64encode(img['data']).decode('utf-8')
                            content_array.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{img['type']};base64,{base64_image}"
                                }
                            })
                        
                        # Replace content string with content array
                        conversation[i]["content"] = content_array
                    
                    break
                    
        # Prepare the request body
        payload = {
            "model": model_to_use,
            "messages": conversation
        }
        
        # Send the request
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://discord-bot.gideon",
                    "X-Title": "Gideon Discord Bot",
                    "X-Client": "openrouter-python"
                }
                
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API Error ({response.status}): {error_text}")
                        return f"⚠️ API Error ({response.status}): {error_text}"
                    
                    result = await response.json()
                    logger.info(f"Response keys: {result.keys()}")
                    
                    try:
                        if "choices" in result and len(result["choices"]) > 0:
                            choice = result["choices"][0]
                            if "message" in choice and "content" in choice["message"]:
                                return choice["message"]["content"]
                            else:
                                logger.error(f"Unexpected choice format: {choice}")
                                return "⚠️ Choice missing message or content field"
                        elif "error" in result:
                            error_msg = result.get("error", {}).get("message", "Unknown error")
                            error_type = result.get("error", {}).get("type", "")
                            
                            logger.error(f"API returned error: {error_msg}, type: {error_type}")
                            
                            # Handle rate limit errors with more user-friendly message
                            if "rate limit" in error_msg.lower() or "ratelimit" in error_msg.lower():
                                return f"⚠️ Rate limit exceeded for model `{self.model}`.\nPlease try:\n- Waiting a few minutes\n- Selecting a different model with `/setmodel`\n- Using a paid plan on OpenRouter"
                            
                            return f"⚠️ API Error: {error_msg}"
                        else:
                            logger.error(f"Unexpected API response format: {result}")
                            return "⚠️ Unexpected API response format. Try using `/setmodel` to switch to a different model."
                    except Exception as e:
                        logger.error(f"Error parsing API response: {str(e)}")
                        return f"⚠️ Error parsing response: {str(e)}"
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return f"⚠️ Error: {str(e)}"