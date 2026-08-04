"""Regression tests for the video resolution selectors."""

import ast
import asyncio
import unittest
from pathlib import Path

from src.utils.openrouter_video_client import OpenRouterVideoClient


REPO_ROOT = Path(__file__).resolve().parents[1]


class VideoResolutionTests(unittest.TestCase):
    def test_discord_commands_offer_2k_resolution(self):
        source = (REPO_ROOT / "src/cogs/video_commands.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        resolution_assignment = next(
            node
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "RESOLUTION_CHOICES" for target in node.targets)
        )
        values = [
            ast.literal_eval(keyword.value)
            for choice in resolution_assignment.value.elts
            for keyword in choice.keywords
            if keyword.arg == "value"
        ]

        self.assertIn("2K", values)

    def test_dashboard_offers_2k_video_resolution(self):
        dashboard = (REPO_ROOT / "src/dashboard/index.html").read_text(encoding="utf-8")

        selector_start = dashboard.index('<select id="video-resolution">')
        selector_end = dashboard.index("</select>", selector_start)
        resolution_selector = dashboard[selector_start:selector_end]

        self.assertIn('<option value="2K">2K</option>', resolution_selector)

    def test_model_autocomplete_uses_existing_openrouter_cache_without_network(self):
        source = (REPO_ROOT / "src/cogs/video_commands.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        video_commands = next(
            node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "VideoCommands"
        )
        get_models = next(
            node
            for node in video_commands.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_get_models"
        )
        get_models_source = ast.get_source_segment(source, get_models)
        video_source = ast.get_source_segment(source, video_commands)

        self.assertEqual([], [node for node in ast.walk(get_models) if isinstance(node, ast.Await)])
        self.assertNotIn("list_video_models", get_models_source)
        self.assertNotIn("create_task", video_source)
        self.assertNotIn("on_ready", video_source)
        self.assertNotIn("_fallback_models", video_source)

    def test_unconfigured_model_listing_does_not_invent_models(self):
        client = OpenRouterVideoClient("")

        result = asyncio.run(client.list_video_models())

        self.assertFalse(result["success"])
        self.assertNotIn("models", result)

    def test_openrouter_video_models_are_filtered_from_canonical_models(self):
        raw_models = [
            {"id": "text/model", "architecture": {"output_modalities": ["text"]}},
            {
                "id": "video/model",
                "name": "Video Model",
                "architecture": {"input_modalities": ["text"], "output_modalities": ["video"]},
            },
        ]

        formatted = [OpenRouterVideoClient.format_video_model(model) for model in raw_models]
        models = [model for model in formatted if model]

        self.assertEqual(["video/model"], [model["id"] for model in models])
        self.assertEqual(["video"], models[0]["output_modalities"])


if __name__ == "__main__":
    unittest.main()
