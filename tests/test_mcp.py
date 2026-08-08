import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from factory.mcp import MCPDiscovery


class MCPTests(unittest.TestCase):
    def test_claude_project_mcp_persists_names_not_secret_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {
                "github": {
                    "type": "http",
                    "url": "https://example.invalid/mcp",
                    "headers": {"Authorization": "Bearer super-secret"},
                    "env": {"GITHUB_TOKEN": "also-secret"},
                }
            }}))
            info = MCPDiscovery(root).inspect()
            serialized = json.dumps(info)
            self.assertIn("github", serialized)
            self.assertIn("Authorization", serialized)
            self.assertIn("GITHUB_TOKEN", serialized)
            self.assertNotIn("super-secret", serialized)
            self.assertNotIn("also-secret", serialized)

    def test_required_mcp_missing_for_provider_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = MCPDiscovery(root).resolve("claude", required=["github"])
            self.assertEqual(result["missing_required"], ["github"])
            self.assertEqual(result["selected"], [])

    def test_provider_specific_selection_does_not_cross_assign(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"claude-only": {"command": "safe-command"}}}))
            codex = root / ".codex" / "config.toml"; codex.parent.mkdir()
            codex.write_text('[mcp_servers.codex-only]\ncommand = "safe"\n')
            discovery = MCPDiscovery(root)
            self.assertEqual(discovery.resolve("claude", required=["claude-only"])["selected"], ["claude-only"])
            self.assertEqual(discovery.resolve("codex", required=["codex-only"])["selected"], ["codex-only"])
            self.assertEqual(discovery.resolve("codex", required=["claude-only"])["missing_required"], ["claude-only"])

    def test_invalid_server_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                MCPDiscovery(Path(td)).resolve("claude", required=["../escape"])


if __name__ == "__main__":
    unittest.main()
