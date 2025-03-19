import aiohttp
import json
import asyncio
import socket
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('openrouter_client')

class OpenRouterClient:
    def __init__(self, api_key, system_prompt=None):
        self.api_key = api_key
        self.system_prompt = system_prompt
        # Updated to ensure correct API endpoint
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        # Alternative endpoints to try if the main one fails
        self.alternative_urls = [
            "https://api.openrouter.ai/api/v1/chat/completions",
            "https://api.openrouter.ai/v1/chat/completions"
        ]
        
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

    async def send_message_with_history(self, message_history, max_retries=3):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://discord-bot"  # OpenRouter requires a referer
        }
        
        # Create messages array with system prompt if available
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        
        # Add conversation history
        messages.extend(message_history)
        
        payload = {
            "model": "openai/gpt-4o-mini",  # Choose an appropriate model
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
                        async with session.post(url, json=payload, headers=headers, timeout=15) as response:
                            if response.status == 200:
                                data = await response.json()
                                return data['choices'][0]['message']['content']
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

    async def get_response(self, message):
        response = await self.send_message(message)
        return response if response else "Error: Unable to get response"