import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory.envs import EnvRouter
from factory.project_adapter import ProjectAdapter
from factory.tools import ToolRegistry
from factory.providers import ProviderRegistry


class DiscoveryTests(unittest.TestCase):
    def test_project_adapter_detects_stack_instructions_and_env_names_only(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "package.json").write_text('{"scripts":{"test":"node test.js","build":"vite build"}}')
            (p / "pyproject.toml").write_text('[project]\nname="x"\n')
            (p / "Dockerfile").write_text('FROM python:3.12')
            (p / "CLAUDE.md").write_text('rules')
            (p / ".env").write_text('SECRET_TOKEN=abc\nPUBLIC_URL=https://x\n# comment\n')
            manifest = ProjectAdapter(p).inspect()
            self.assertIn("node", manifest["stacks"])
            self.assertIn("python", manifest["stacks"])
            self.assertIn("docker", manifest["stacks"])
            self.assertIn("CLAUDE.md", manifest["instruction_files"])
            self.assertIn("SECRET_TOKEN", manifest["env_names"])
            text = str(manifest)
            self.assertNotIn("abc", text)

    def test_subscription_env_removes_api_keys(self):
        env = {"PATH":"/bin", "HOME":"/tmp", "ANTHROPIC_API_KEY":"a", "OPENAI_API_KEY":"b", "SAFE":"yes"}
        sanitized = EnvRouter(subscription_only=True).sanitize_provider_env(env)
        self.assertNotIn("ANTHROPIC_API_KEY", sanitized)
        self.assertNotIn("OPENAI_API_KEY", sanitized)
        self.assertEqual(sanitized["PATH"], "/bin")

    def test_tool_registry_and_provider_discovery_are_adaptive(self):
        def fake_which(name):
            return f"/usr/bin/{name}" if name in {"git","claude"} else None
        with mock.patch("shutil.which", side_effect=fake_which):
            tools = ToolRegistry.discover()
            providers = ProviderRegistry.discover()
        self.assertTrue(tools["git"]["available"])
        self.assertFalse(tools["docker"]["available"])
        self.assertTrue(providers["claude"]["available"])
        self.assertFalse(providers["codex"]["available"])

if __name__ == "__main__": unittest.main()
