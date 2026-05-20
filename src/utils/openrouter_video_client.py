"""Client for interacting with OpenRouter API for video generation.

OpenRouter exposes an asynchronous video generation API at /api/v1/videos.
The flow is:
    1. Submit a generation job (POST /api/v1/videos) with model + prompt and
       optional normalized parameters (aspect_ratio, duration, resolution,
       audio, image inputs, etc.).
    2. Poll the job (GET /api/v1/videos/{id}) until status is `completed`
       or a terminal failure state.
    3. Download the resulting video from the `unsigned_urls` array.

Reference: https://openrouter.ai/docs/guides/overview/multimodal/video-generation
"""
import aiohttp
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger('openrouter_video_client')

TERMINAL_STATUSES = {"completed", "failed", "canceled", "cancelled", "error"}


class OpenRouterVideoClient:
    """Client for generating videos via OpenRouter's unified video API."""

    def __init__(self, api_key: str):
        if not api_key:
            logger.warning("OpenRouter API key is not configured. Video generation will not work.")
            self.api_key = None
        else:
            self.api_key = api_key
            logger.info("OpenRouter Video client initialized successfully.")
        self.base_url = "https://openrouter.ai/api/v1"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _parse_error(status: int, text: str) -> Dict[str, Any]:
        """Build a uniform error dict from an HTTP error response."""
        msg = text or ""
        try:
            data = json.loads(text) if text else {}
            if isinstance(data, dict):
                err = data.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("code") or msg
                elif isinstance(err, str):
                    msg = err
                else:
                    msg = data.get("message") or msg
        except (json.JSONDecodeError, TypeError):
            pass
        return {"success": False, "error": f"OpenRouter API error ({status}): {str(msg)[:300]}"}

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/eoko-dev/gideon",
            "X-Title": "Gideon Discord Bot",
        }

    async def submit_video(
        self,
        prompt: str,
        model: str,
        aspect_ratio: Optional[str] = None,
        duration: Optional[int] = None,
        resolution: Optional[str] = None,
        seed: Optional[int] = None,
        audio: Optional[bool] = None,
        image: Optional[str] = None,
        callback_url: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit a video generation job.

        Args:
            prompt: Text description of the video.
            model: OpenRouter video model id (e.g. "google/veo-3.1").
            aspect_ratio: e.g. "16:9", "9:16", "1:1".
            duration: Duration in seconds.
            resolution: e.g. "480p", "720p", "1080p", "4K".
            seed: Optional seed for reproducibility.
            audio: Whether to generate audio (model dependent).
            image: Optional URL or base64 data URL of a reference/start frame.
            callback_url: Webhook URL for terminal-state notifications.
            extra: Model-specific extra parameters (merged into request body).

        Returns:
            Dict with success, job_id, status, polling_url, raw on success.
        """
        if not self.is_configured:
            return {"success": False, "error": "OpenRouter client is not initialized (API key missing or invalid)."}
        if not model:
            return {"success": False, "error": "No model specified. OpenRouter requires an explicit model selection."}
        if not prompt:
            return {"success": False, "error": "Prompt is required."}

        payload: Dict[str, Any] = {"model": model, "prompt": prompt}
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        if duration is not None:
            payload["duration"] = duration
        if resolution:
            payload["resolution"] = resolution
        if seed is not None:
            payload["seed"] = seed
        if audio is not None:
            payload["audio"] = audio
        if image:
            payload["image"] = image
        if callback_url:
            payload["callback_url"] = callback_url
        if extra:
            for k, v in extra.items():
                if v is not None:
                    payload[k] = v

        logger.info(f"Submitting OpenRouter video job: model={model}")
        logger.debug(f"Submit payload: {json.dumps(payload, default=str)}")

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/videos",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    text = await response.text()
                    if response.status not in (200, 201, 202):
                        return self._parse_error(response.status, text)
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        return {"success": False, "error": f"Invalid JSON in response: {text[:200]}"}

                    job_id = data.get("id") or data.get("job_id") or data.get("video_id")
                    status = data.get("status", "queued")
                    polling_url = data.get("polling_url") or data.get("url")
                    if not job_id:
                        return {"success": False, "error": f"No job id in response: {text[:200]}"}

                    return {
                        "success": True,
                        "job_id": job_id,
                        "status": status,
                        "polling_url": polling_url,
                        "raw": data,
                    }
        except aiohttp.ClientError as e:
            logger.error(f"Network error submitting OpenRouter video job: {e}")
            return {"success": False, "error": f"Network error: {e}"}
        except Exception as e:
            logger.exception(f"Unexpected error submitting OpenRouter video job: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}

    async def get_video_status(self, job_id: str) -> Dict[str, Any]:
        """Poll a video generation job's status."""
        if not self.is_configured:
            return {"success": False, "error": "OpenRouter client is not initialized."}
        if not job_id:
            return {"success": False, "error": "job_id is required."}

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/videos/{job_id}",
                    headers=self._headers(),
                ) as response:
                    text = await response.text()
                    if response.status != 200:
                        return self._parse_error(response.status, text)
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        return {"success": False, "error": f"Invalid JSON in response: {text[:200]}"}

                    status = data.get("status", "unknown")
                    unsigned_urls = data.get("unsigned_urls") or []
                    return {
                        "success": True,
                        "status": status,
                        "unsigned_urls": unsigned_urls,
                        "raw": data,
                    }
        except aiohttp.ClientError as e:
            logger.error(f"Network error polling video job {job_id}: {e}")
            return {"success": False, "error": f"Network error: {e}"}
        except Exception as e:
            logger.exception(f"Unexpected error polling video job {job_id}: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 15.0,
        timeout: float = 900.0,
        on_status: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Poll until the job reaches a terminal state or timeout elapses.

        Args:
            job_id: Job id returned by submit_video.
            poll_interval: Seconds between polls.
            timeout: Total max wait in seconds.
            on_status: Optional async callback invoked with each poll result
                (a dict like {status, raw, ...}). Useful for progress updates.

        Returns the final status dict (success path) or a failure dict.
        """
        elapsed = 0.0
        last: Dict[str, Any] = {}
        while elapsed < timeout:
            result = await self.get_video_status(job_id)
            last = result
            if not result.get("success"):
                return result
            if on_status is not None:
                try:
                    await on_status(result)
                except Exception:
                    logger.debug("on_status callback raised", exc_info=True)
            status = result.get("status", "")
            if status in TERMINAL_STATUSES:
                return result
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        return {
            "success": False,
            "error": f"Timed out after {int(timeout)}s waiting for video job {job_id}",
            "last": last,
        }

    def _download_headers(self) -> Dict[str, str]:
        """Minimal headers for downloading OpenRouter-hosted video files.

        OpenRouter's unsigned_urls still pass through their auth layer, so the
        API key must be present. Content-Type is intentionally omitted (not
        appropriate for a GET download request).
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/eoko-dev/gideon",
            "X-Title": "Gideon Discord Bot",
        }

    async def download_video(self, url: str) -> Dict[str, Any]:
        """Download a generated video's bytes from a (signed or unsigned) URL."""
        if not url:
            return {"success": False, "error": "Empty URL"}
        try:
            timeout = aiohttp.ClientTimeout(total=300)
            headers = self._download_headers() if self.is_configured else {}
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        text = await response.text()
                        return {"success": False, "error": f"Download failed ({response.status}): {text[:200]}"}
                    data = await response.read()
                    content_type = response.headers.get("Content-Type", "video/mp4")
                    return {"success": True, "data": data, "content_type": content_type}
        except aiohttp.ClientError as e:
            return {"success": False, "error": f"Network error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    async def list_video_models(self) -> Dict[str, Any]:
        """Fetch the list of available video generation models.

        Falls back to a curated list if the live endpoint is unreachable.
        """
        fallback = self._fallback_models()
        if not self.is_configured:
            return {"success": True, "models": fallback, "source": "fallback"}

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/videos/models",
                    headers=self._headers(),
                ) as response:
                    if response.status != 200:
                        logger.warning(f"video models endpoint returned {response.status}; using fallback")
                        return {"success": True, "models": fallback, "source": "fallback"}
                    data = await response.json()
                    raw = data.get("data") if isinstance(data, dict) else data
                    if not isinstance(raw, list):
                        return {"success": True, "models": fallback, "source": "fallback"}
                    models: List[Dict[str, Any]] = []
                    for m in raw:
                        if not isinstance(m, dict):
                            continue
                        model_id = m.get("id") or m.get("model")
                        if not model_id:
                            continue
                        models.append({
                            "id": model_id,
                            "name": m.get("name") or model_id,
                            "supported_resolutions": m.get("supported_resolutions") or m.get("resolutions") or [],
                            "supported_aspect_ratios": m.get("supported_aspect_ratios") or m.get("aspect_ratios") or [],
                            "supported_durations": m.get("supported_durations") or m.get("durations") or [],
                            "supports_audio": m.get("supports_audio"),
                            "supports_image_input": m.get("supports_image_input"),
                            "pricing": m.get("pricing"),
                        })
                    if not models:
                        return {"success": True, "models": fallback, "source": "fallback"}
                    return {"success": True, "models": models, "source": "api"}
        except Exception as e:
            logger.warning(f"Failed to fetch video models from OpenRouter: {e}; using fallback list")
            return {"success": True, "models": fallback, "source": "fallback"}

    @staticmethod
    def _fallback_models() -> List[Dict[str, Any]]:
        """Curated fallback list of OpenRouter video generation models.

        OpenRouter advertises (per the announcement post): Seedance 2.0 / 1.5,
        Veo 3.1, Wan 2.7 / 2.6, and Sora 2 Pro. The /api/v1/videos/models
        endpoint is the source of truth at runtime; this list keeps the UI
        usable when the endpoint is unreachable.
        """
        return [
            {
                "id": "google/veo-3.1",
                "name": "Veo 3.1 (Google)",
                "supported_resolutions": ["720p", "1080p"],
                "supported_aspect_ratios": ["16:9", "9:16"],
                "supported_durations": [4, 6, 8],
                "supports_audio": True,
                "supports_image_input": True,
            },
            {
                "id": "google/veo-3",
                "name": "Veo 3 (Google)",
                "supported_resolutions": ["720p", "1080p"],
                "supported_aspect_ratios": ["16:9", "9:16"],
                "supported_durations": [4, 6, 8],
                "supports_audio": True,
                "supports_image_input": True,
            },
            {
                "id": "openai/sora-2-pro",
                "name": "Sora 2 Pro (OpenAI)",
                "supported_resolutions": ["720p", "1080p"],
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_durations": [5, 10],
                "supports_audio": True,
                "supports_image_input": True,
            },
            {
                "id": "bytedance/seedance-2.0",
                "name": "Seedance 2.0 (ByteDance)",
                "supported_resolutions": ["480p", "720p", "1080p"],
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_durations": [5, 10],
                "supports_audio": False,
                "supports_image_input": True,
            },
            {
                "id": "bytedance/seedance-1.5",
                "name": "Seedance 1.5 (ByteDance)",
                "supported_resolutions": ["480p", "720p"],
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_durations": [5, 10],
                "supports_audio": False,
                "supports_image_input": True,
            },
            {
                "id": "alibaba/wan-2.7",
                "name": "Wan 2.7 (Alibaba)",
                "supported_resolutions": ["480p", "720p"],
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_durations": [4, 5, 6, 8],
                "supports_audio": False,
                "supports_image_input": True,
            },
            {
                "id": "alibaba/wan-2.6",
                "name": "Wan 2.6 (Alibaba)",
                "supported_resolutions": ["480p", "720p"],
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_durations": [4, 5, 6, 8],
                "supports_audio": False,
                "supports_image_input": True,
            },
            {
                "id": "kwaivgi/kling-video-o1",
                "name": "Kling Video O1 (Kuaishou)",
                "supported_resolutions": ["720p", "1080p"],
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_durations": [5, 10],
                "supports_audio": False,
                "supports_image_input": True,
            },
        ]
