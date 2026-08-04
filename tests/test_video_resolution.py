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

    def test_model_autocomplete_starts_live_refresh_without_awaiting_network(self):
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

        awaited_calls = [node for node in ast.walk(get_models) if isinstance(node, ast.Await)]
        self.assertEqual([], awaited_calls)

        refresh_calls = [
            node
            for node in ast.walk(get_models)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_start_models_refresh"
        ]
        self.assertEqual(1, len(refresh_calls))

        video_source = ast.get_source_segment(source, video_commands)
        self.assertNotIn("_fallback_models", video_source)

    def test_unconfigured_model_listing_does_not_invent_models(self):
        client = OpenRouterVideoClient("")

        result = asyncio.run(client.list_video_models())

        self.assertFalse(result["success"])
        self.assertNotIn("models", result)


if __name__ == "__main__":
    unittest.main()
