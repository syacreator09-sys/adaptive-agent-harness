import os
import unittest
from unittest import mock
from factory.tools import ToolRegistry


class ToolRouterTests(unittest.TestCase):
    def test_claude_web_maps_to_native_web_tools(self):
        result = ToolRegistry.resolve(["web"], discovered={}, provider="claude")
        self.assertEqual(result["missing"], [])
        self.assertIn("WebSearch", result["provider_tools"])
        self.assertIn("WebFetch", result["provider_tools"])

    def test_codex_web_requires_explicit_adapter(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = ToolRegistry.resolve(["web"], discovered={}, provider="codex")
        self.assertIn("web", result["missing"])

    def test_adapter_command_value_is_not_in_discovery_metadata(self):
        secret_command = "tool --token do-not-persist"
        with mock.patch.dict(os.environ, {"AAH_TOOL_IMAGE": secret_command}, clear=True):
            discovered = ToolRegistry.discover()
            self.assertTrue(discovered["adapter:image"]["available"])
            self.assertNotIn(secret_command, str(discovered))
            resolved = ToolRegistry.resolve(["image"], discovered=discovered, provider="codex")
        self.assertEqual(resolved["adapters"]["image"]["env"], "AAH_TOOL_IMAGE")
        self.assertEqual(resolved["adapters"]["image"]["invoke"], ".aah/bin/tool-adapter image")
        self.assertNotIn(secret_command, str(resolved))

    def test_missing_required_local_capability_is_reported(self):
        result = ToolRegistry.resolve(["docker"], discovered={"docker": {"available": False}}, provider="claude")
        self.assertEqual(result["missing"], ["docker"])


if __name__ == "__main__":
    unittest.main()
