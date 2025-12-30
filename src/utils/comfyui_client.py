"""Client for interacting with ComfyUI API for image generation."""
import aiohttp
import asyncio
import copy
import json
import logging
import os
import random
import uuid
from typing import Dict, Any, Optional, List

logger = logging.getLogger('comfyui_client')


class ComfyUIClient:
    """Client for generating images using ComfyUI API."""

    # Default workflow for txt2img generation
    DEFAULT_WORKFLOW = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 7.0,
                "denoise": 1.0,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "seed": 0,
                "steps": 20
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "v1-5-pruned-emaonly.safetensors"
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": 512,
                "width": 512
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": ""
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": ""
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": ["8", 0]
            }
        }
    }

    def __init__(self, api_url: str):
        """
        Initialize ComfyUI client.

        Args:
            api_url: Base URL of ComfyUI server (e.g., "http://127.0.0.1:8188")
        """
        self.api_url = api_url.rstrip('/')
        self.client_id = str(uuid.uuid4())

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to ComfyUI server."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/system_stats",
                    timeout=10
                ) as response:
                    if response.status != 200:
                        return {"success": False, "error": f"HTTP {response.status}"}

                    stats = await response.json()
                    return {
                        "success": True,
                        "system_stats": stats
                    }
        except aiohttp.ClientError as e:
            logger.error(f"Connection test failed: {e}")
            return {"success": False, "error": f"Connection failed: {str(e)}"}
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            return {"success": False, "error": str(e)}

    async def generate_image(self,
                            prompt: str,
                            negative_prompt: str = "",
                            width: int = 512,
                            height: int = 512,
                            steps: int = 20,
                            seed: Optional[int] = None,
                            model: Optional[str] = None,
                            workflow_json: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate an image using ComfyUI.

        Args:
            prompt: Text description of the desired image
            negative_prompt: What the image should not contain
            width: Image width
            height: Image height
            steps: Number of generation steps
            seed: Random seed for reproducibility (optional)
            model: Checkpoint model name (optional)
            workflow_json: Custom workflow JSON string (optional)

        Returns:
            Dict with "success", "image_data" (bytes), "seed", "model" keys
            Or Dict with "error" key on failure
        """
        try:
            # Load workflow
            if workflow_json:
                try:
                    workflow = json.loads(workflow_json)
                except json.JSONDecodeError as e:
                    return {"error": f"Invalid workflow JSON: {str(e)}"}
            else:
                workflow = copy.deepcopy(self.DEFAULT_WORKFLOW)

            # Generate seed if not provided
            actual_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

            # Inject parameters into workflow
            workflow = self._inject_parameters(
                workflow, prompt, negative_prompt,
                width, height, steps, actual_seed, model
            )

            # Submit prompt to ComfyUI
            prompt_id = await self._submit_prompt(workflow)

            if not prompt_id:
                return {"error": "Failed to submit prompt to ComfyUI"}

            # Poll for completion
            result = await self._poll_for_completion(prompt_id)

            if "error" in result:
                return result

            # Extract image info from outputs
            outputs = result.get("outputs", {})
            image_info = self._extract_image_info(outputs)

            if not image_info:
                return {"error": "No image output found in workflow result"}

            # Retrieve the image
            image_data = await self._retrieve_image(
                image_info["filename"],
                image_info.get("subfolder", ""),
                image_info.get("type", "output")
            )

            if image_data is None:
                return {"error": "Failed to retrieve generated image"}

            return {
                "success": True,
                "image_data": image_data,
                "seed": actual_seed,
                "model": model or "default"
            }

        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            return {"error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.exception(f"Error generating image: {e}")
            return {"error": f"Error: {str(e)}"}

    async def get_available_models(self, model_type: str = "checkpoints") -> Dict[str, Any]:
        """
        Get list of available models from ComfyUI.

        Args:
            model_type: "checkpoints", "loras", "vae", etc.

        Returns:
            Dict with "success" and "models" list, or "error"
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Try the /models endpoint first
                async with session.get(
                    f"{self.api_url}/models/{model_type}",
                    timeout=30
                ) as response:
                    if response.status == 200:
                        models = await response.json()
                        return {
                            "success": True,
                            "models": [{"id": m, "name": m} for m in models]
                        }

                # Fallback to /object_info
                return await self._get_models_from_object_info(session, model_type)

        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return {"success": False, "error": str(e)}

    async def _get_models_from_object_info(self, session: aiohttp.ClientSession,
                                           model_type: str) -> Dict[str, Any]:
        """Fallback: get model list from /object_info endpoint."""
        try:
            async with session.get(f"{self.api_url}/object_info") as response:
                if response.status != 200:
                    return {"success": False, "error": "Could not query models"}

                info = await response.json()

                # Map model_type to node class and input field
                node_map = {
                    "checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
                    "loras": ("LoraLoader", "lora_name"),
                    "vae": ("VAELoader", "vae_name")
                }

                if model_type not in node_map:
                    return {"success": False, "error": f"Unknown model type: {model_type}"}

                node_name, input_field = node_map[model_type]

                if node_name in info:
                    node_info = info[node_name]
                    inputs = node_info.get("input", {}).get("required", {})
                    if input_field in inputs:
                        models = inputs[input_field][0]  # First element is list of options
                        return {
                            "success": True,
                            "models": [{"id": m, "name": m} for m in models]
                        }

                return {"success": False, "error": f"No models found for type: {model_type}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _submit_prompt(self, workflow: Dict) -> Optional[str]:
        """Submit workflow to ComfyUI /prompt endpoint."""
        payload = {
            "prompt": workflow,
            "client_id": self.client_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/prompt",
                json=payload,
                timeout=30
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to submit prompt: {response.status} - {error_text}")
                    return None

                result = await response.json()
                return result.get("prompt_id")

    async def _poll_for_completion(self, prompt_id: str,
                                   timeout: int = 600,
                                   poll_interval: float = 1.0) -> Dict[str, Any]:
        """Poll /history endpoint until execution completes (default 10 min timeout)."""
        start_time = asyncio.get_event_loop().time()

        async with aiohttp.ClientSession() as session:
            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    async with session.get(
                        f"{self.api_url}/history/{prompt_id}",
                        timeout=10
                    ) as response:
                        if response.status != 200:
                            await asyncio.sleep(poll_interval)
                            continue

                        history = await response.json()

                        if prompt_id in history:
                            entry = history[prompt_id]

                            # Check for execution error
                            status = entry.get("status", {})
                            if status.get("status_str") == "error":
                                messages = status.get("messages", [])
                                error_text = str(messages)

                                # Parse specific error types
                                if "out of memory" in error_text.lower():
                                    return {"error": "GPU out of memory. Try smaller image size or fewer steps."}
                                elif "checkpoint" in error_text.lower() and "not found" in error_text.lower():
                                    return {"error": "Model not found. Use /dream_manage comfyui_models to see available models."}
                                else:
                                    return {"error": f"Generation failed: {messages}"}

                            # Check if outputs exist (execution complete)
                            if "outputs" in entry and entry["outputs"]:
                                return {"success": True, "outputs": entry["outputs"]}

                except aiohttp.ClientError:
                    pass  # Continue polling on network errors

                await asyncio.sleep(poll_interval)

        return {"error": f"Generation timed out after {timeout} seconds"}

    async def _retrieve_image(self, filename: str,
                             subfolder: str = "",
                             folder_type: str = "output") -> Optional[bytes]:
        """Retrieve generated image from /view endpoint."""
        params = {
            "filename": filename,
            "type": folder_type
        }
        if subfolder:
            params["subfolder"] = subfolder

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_url}/view",
                params=params,
                timeout=30
            ) as response:
                if response.status != 200:
                    logger.error(f"Failed to retrieve image: {response.status}")
                    return None

                return await response.read()

    def _inject_parameters(self, workflow: Dict,
                          prompt: str,
                          negative_prompt: str,
                          width: int,
                          height: int,
                          steps: int,
                          seed: int,
                          model: Optional[str]) -> Dict:
        """Inject generation parameters into workflow nodes."""
        workflow = copy.deepcopy(workflow)

        # Track which CLIP nodes we've found for positive/negative
        clip_nodes = []

        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})

            if class_type == "CLIPTextEncode":
                clip_nodes.append((node_id, inputs))

            # Sampler settings
            elif class_type == "KSampler":
                inputs["seed"] = seed
                inputs["steps"] = steps

            # Latent image size
            elif class_type == "EmptyLatentImage":
                inputs["width"] = width
                inputs["height"] = height

            # Checkpoint model
            elif class_type == "CheckpointLoaderSimple" and model:
                inputs["ckpt_name"] = model

        # Assign prompts to CLIP nodes
        # Convention: first CLIP node is positive, second is negative
        # Or check by node ID (6 = positive, 7 = negative in default workflow)
        if len(clip_nodes) >= 2:
            # Sort by node ID to ensure consistent ordering
            clip_nodes.sort(key=lambda x: x[0])
            clip_nodes[0][1]["text"] = prompt
            clip_nodes[1][1]["text"] = negative_prompt
        elif len(clip_nodes) == 1:
            clip_nodes[0][1]["text"] = prompt

        return workflow

    def _extract_image_info(self, outputs: Dict) -> Optional[Dict[str, str]]:
        """Extract image filename and location from workflow outputs."""
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                images = node_output["images"]
                if images and len(images) > 0:
                    img = images[0]
                    return {
                        "filename": img.get("filename"),
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output")
                    }
        return None
