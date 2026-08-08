import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from factory.project_adapter import ProjectAdapter


class ProjectAdapterV2Tests(unittest.TestCase):
    def test_detects_stack_commands_env_names_and_safe_mcp_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest", "build": "vite build"}}))
            (root / ".env.local").write_text("DATABASE_URL=postgres://do-not-store\nPUBLIC_URL=https://example.test\n")
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {
                "docs": {"command": "docs-mcp", "env": {"DOCS_TOKEN": "do-not-store"}}
            }}))
            info = ProjectAdapter(root).inspect()
            self.assertIn("node", info["stacks"])
            self.assertEqual(info["commands"]["test"], "npm run test")
            self.assertEqual(info["commands"]["build"], "npm run build")
            self.assertEqual(info["env_classes"]["DATABASE_URL"], "secret")
            self.assertEqual(info["mcp"]["servers"][0]["name"], "docs")
            serialized = json.dumps(info)
            self.assertNotIn("postgres://do-not-store", serialized)
            self.assertNotIn("do-not-store", serialized)

    def test_git_repo_is_detected_without_requiring_dot_git_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            info = ProjectAdapter(root).inspect()
            self.assertTrue(info["git"]["is_repo"])


if __name__ == "__main__":
    unittest.main()
