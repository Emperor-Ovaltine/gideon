import aiohttp
import json
import asyncio
import socket
import logging
import base64
from io import BytesIO
from typing import List, Dict, Any, Optional

logger = logging.getLogger('openrouter_client')

class OpenRouterClient:
    """Client for interacting with the OpenRouter API."""
    
    def __init__(self, api_key: str, system_prompt: str, default_model: str):
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.model = default_model
        self.base_url = "https://openrouter.ai/api/v1"
        self._session: Optional[aiohttp.ClientSession] = None
        
        # List of model name fragments that support vision
        self.vision_models = [
            "claude-3",
            "gpt-4", # Make more general to catch gpt-4o, etc.
            "gemini",
            "llava", # Add Llava models
        ]
        
    def model_supports_vision(self, model_name: Optional[str] = None) -> bool:
        """Check if the given model (or the default) supports vision/images."""
        model_to_check = (model_name or self.model or "").lower()
        return any(vision_model in model_to_check for vision_model in self.vision_models)

    def _get_session(self) -> aiohttp.ClientSession:
        """Returns the shared HTTP session, creating it lazily.

        One session per client keeps the connection pool warm across
        requests and applies a sane default timeout.
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120)
            )
        return self._session

    async def close(self):
        """Closes the shared HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
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
        model: Optional[str] = None,
        web_search: bool = False,
        response_format: Optional[Dict[str, Any]] = None, # Add response_format parameter
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> str:
        """Send a message with conversation history to the AI model."""
        # Use provided system prompt or fall back to default
        prompt_to_use = system_prompt if system_prompt is not None else self.system_prompt
        
        # Use provided model or fall back to the default
        model_to_use = model if model is not None else self.model
        
        # Add logging
        logger.info(f"Using model: {model_to_use}")
        logger.info(f"System prompt length: {len(prompt_to_use)}")
        logger.info(f"Web search enabled: {web_search}")
        
        # Prepare the full conversation context with system prompt
        conversation = [{"role": "system", "content": prompt_to_use}]
        
        # Add the message history
        conversation.extend(messages)
        
        # If we have images and the model supports them, attach to the last
        # user message using the OpenAI-style content array — OpenRouter
        # normalizes this for every underlying provider (including Claude).
        if images and self.model_supports_vision(model_to_use):
            for i in range(len(conversation) - 1, -1, -1):
                if conversation[i]["role"] == "user":
                    content_array = [{"type": "text", "text": conversation[i]["content"]}]
                    for img in images:
                        base64_image = base64.b64encode(img['data']).decode('utf-8')
                        content_array.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{img['type']};base64,{base64_image}"
                            }
                        })
                    conversation[i]["content"] = content_array
                    break
                    
        # Prepare the request body
        # Strip the "openrouter/" prefix if present, as the API expects the base model ID
        api_model_name = model_to_use
        if api_model_name.startswith("openrouter/"):
            api_model_name = api_model_name.split("/", 1)[1]
            logger.info(f"Using OpenRouter API model name: {api_model_name}")

        payload = {
            "model": api_model_name, # Use the potentially stripped name
            "messages": conversation
        }

        # Add web search parameter if enabled using the 'plugins' field
        if web_search:
            payload["plugins"] = [{"id": "web"}]

        # Add response_format to the payload if provided
        if response_format:
            payload["response_format"] = response_format
            logger.info(f"Using response_format: {response_format.get('type')}") # Log the type being used

        # Add tools to the payload if provided (native function/tool calling)
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
            else:
                payload["tool_choice"] = "auto"
            logger.info(f"Tool calling enabled with {len(tools)} tool(s)")

        # Send the request
        try:
            session = self._get_session()
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/eoko-dev/gideon",
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
                        if "message" in choice:
                            message = choice["message"]
                            # Check for tool calls first
                            if message.get("tool_calls"):
                                logger.info(f"Model requested {len(message['tool_calls'])} tool call(s)")
                                return {
                                    "content": message.get("content"),
                                    "tool_calls": message["tool_calls"]
                                }
                            elif "content" in message:
                                return message["content"]
                            else:
                                logger.error(f"Unexpected choice format: {choice}")
                                return "⚠️ Choice missing message or content field"
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

    async def get_available_models(self) -> Dict[str, Any]:
        """Fetch available models from OpenRouter API."""
        try:
            session = self._get_session()
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/eoko-dev/gideon",
                "X-Title": "Gideon Discord Bot"
            }
            async with session.get(
                f"{self.base_url}/models",
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to get models: ({response.status}) {error_text}")
                    return {"success": False, "error": f"API Error ({response.status}): {error_text}"}
                    
                models_data = await response.json()
                    
                # Process data to extract useful info and identify vision-capable models
                processed_models = []
                vision_models = []
                    
                for model in models_data.get("data", []):
                    model_id = model.get("id")
                    context_length = model.get("context_length", 0)
                    pricing = model.get("pricing", {})
                        
                    # Check if model supports vision based on capabilities
                    # Check if model supports vision based on capabilities OR known identifiers
                    supports_vision = False
                    # 1. Check the capabilities field from API (if present)
                    if model.get("capabilities", {}).get("vision", False):
                        supports_vision = True
                    # 2. Check if model ID matches known vision model patterns (fallback)
                    elif model_id and any(vision_pattern in model_id.lower() for vision_pattern in self.vision_models):
                         supports_vision = True
                         # Log if we used the fallback
                         logger.debug(f"Identified vision support for '{model_id}' using fallback pattern matching.")

                    # Keep track of models identified as vision-capable by the API check (for logging/debugging if needed)
                    if supports_vision:
                         vision_models.append(model_id) # Note: This local list is not used further after this loop

                    processed_models.append({
                        "id": model_id,
                        "name": model.get("name", "Unknown"),
                        "description": model.get("description", ""),
                        "context_length": context_length,
                        "supports_vision": supports_vision, # This is the flag used by ModelManager
                        "pricing": pricing
                    })
                    
                # DO NOT dynamically update self.vision_models here.
                # Keep the original hardcoded list for the client's internal checks.
                # self.vision_models = vision_models
                    
                return {
                    "success": True,
                    "models": processed_models,
                    "raw_data": models_data
                }
        except Exception as e:
            logger.error(f"Error getting models: {str(e)}")
            return {"success": False, "error": f"Error getting models: {str(e)}"}