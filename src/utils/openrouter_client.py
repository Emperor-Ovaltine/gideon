import aiohttp
import json
import asyncio
import socket
import logging
import base64
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Dict, Any, Optional

from .llm_formatting import prepare_llm_messages

logger = logging.getLogger('openrouter_client')

class OpenRouterClient:
    """Client for interacting with the OpenRouter API."""
    
    def __init__(self, api_key: str, system_prompt: str, default_model: str):
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.model = default_model
        self.base_url = "https://openrouter.ai/api/v1"
        self._session: Optional[aiohttp.ClientSession] = None

        # Vision capability is read from the /models API rather than a
        # maintained list. Populated as a side effect of get_available_models().
        self._vision_capabilities: Dict[str, bool] = {}
        self._capabilities_updated: Optional[datetime] = None
        self._capabilities_ttl = timedelta(hours=12)
        self._capabilities_lock = asyncio.Lock()

    @staticmethod
    def _detect_vision_support(model_info: Dict[str, Any]) -> Optional[bool]:
        """Read image-input support from a /models entry.

        Returns None when the entry carries no modality metadata at all, so
        callers can tell "known to be text-only" apart from "don't know".
        """
        architecture = model_info.get("architecture") or {}

        input_modalities = architecture.get("input_modalities")
        if isinstance(input_modalities, list) and input_modalities:
            return "image" in [str(m).lower() for m in input_modalities]

        # Older entries only carry a combined string like "text+image->text".
        modality_str = architecture.get("modality") or ""
        if "->" in modality_str:
            return "image" in modality_str.split("->")[0].lower()

        return None

    def _normalize_model_id(self, model_name: Optional[str] = None) -> str:
        """Resolve a model name to the ID used by the OpenRouter API."""
        model_id = model_name or self.model or ""
        if model_id.startswith("openrouter/"):
            model_id = model_id.split("/", 1)[1]
        return model_id

    async def _ensure_capabilities(self) -> None:
        """Populate the capability map, refreshing it once the TTL expires."""
        def is_stale() -> bool:
            return (
                self._capabilities_updated is None
                or datetime.now() - self._capabilities_updated > self._capabilities_ttl
            )

        if self._vision_capabilities and not is_stale():
            return

        async with self._capabilities_lock:
            # Another waiter may have refreshed while we queued on the lock.
            if self._vision_capabilities and not is_stale():
                return
            # Errors are logged by get_available_models; a failed refresh
            # leaves any previously fetched map in place.
            await self.get_available_models()

    async def model_supports_vision(self, model_name: Optional[str] = None) -> bool:
        """Check if the given model (or the default) accepts image input."""
        model_to_check = self._normalize_model_id(model_name)

        await self._ensure_capabilities()

        if model_to_check in self._vision_capabilities:
            return self._vision_capabilities[model_to_check]

        # Unknown model, or the models API is unreachable. Assume vision is
        # supported so the request goes out and any rejection is visible,
        # rather than silently dropping the image the user attached.
        logger.warning(
            f"No capability metadata for '{model_to_check}'; assuming image input is supported"
        )
        return True

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
        
        # Add the message history, labelling each user turn with its speaker
        # and dropping bookkeeping keys the API doesn't accept
        conversation.extend(prepare_llm_messages(messages))
        
        # If we have images and the model supports them, attach to the last
        # user message using the OpenAI-style content array — OpenRouter
        # normalizes this for every underlying provider (including Claude).
        if images and await self.model_supports_vision(model_to_use):
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

                for model in models_data.get("data", []):
                    model_id = model.get("id")
                    context_length = model.get("context_length", 0)
                    pricing = model.get("pricing", {})
                    architecture = model.get("architecture") or {}

                    # Models advertised as vision-capable are only those the API
                    # confirms; unknown metadata is treated as "no" here, while
                    # the per-model runtime check errs the other way.
                    supports_vision = self._detect_vision_support(model) is True

                    processed_models.append({
                        "id": model_id,
                        "name": model.get("name", "Unknown"),
                        "description": model.get("description", ""),
                        "context_length": context_length,
                        "supports_vision": supports_vision, # This is the flag used by ProviderManager
                        "input_modalities": architecture.get("input_modalities", []),
                        "output_modalities": architecture.get("output_modalities", []),
                        "modality": architecture.get("modality", ""),
                        "pricing": pricing
                    })

                self._vision_capabilities = {
                    m["id"]: m["supports_vision"] for m in processed_models if m["id"]
                }
                self._capabilities_updated = datetime.now()
                logger.info(
                    f"Loaded capabilities for {len(self._vision_capabilities)} models "
                    f"({sum(self._vision_capabilities.values())} accept image input)"
                )

                return {
                    "success": True,
                    "models": processed_models,
                    "raw_data": models_data
                }
        except Exception as e:
            logger.error(f"Error getting models: {str(e)}")
            return {"success": False, "error": f"Error getting models: {str(e)}"}