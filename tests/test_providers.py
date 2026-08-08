import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from factory.providers import ClaudeProvider, CodexProvider, ProviderRegistry, ProviderError
from factory.codex_profiles import install_profiles


class ProviderCommandTests(unittest.TestCase):
    @mock.patch("factory.providers.subprocess.run")
    def test_claude_restricts_role_tools_and_disables_unrequested_mcp(self, run):
        run.return_value = mock.Mock(returncode=0, stdout=json.dumps({"result": "{}"}), stderr="")
        ClaudeProvider().run("x", Path("."), model="sonnet", tools=["Read", "Bash"], guardian="guarded")
        cmd = run.call_args.args[0]
        self.assertIn("--tools", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Bash")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertNotIn("--mcp-config", cmd)
        self.assertIn("--allowedTools", cmd)
        allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--permission-mode")]
        self.assertEqual(allowed, ["Read", "Bash"])
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "dontAsk")

    @mock.patch("factory.providers.subprocess.run")
    def test_claude_empty_role_tools_stays_empty_instead_of_restoring_defaults(self, run):
        run.return_value = mock.Mock(returncode=0, stdout=json.dumps({"result": "{}"}), stderr="")
        ClaudeProvider().run("x", Path("."), tools=[])
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertNotIn("--allowedTools", cmd)
        self.assertIn("--strict-mcp-config", cmd)

    @mock.patch("factory.providers.subprocess.run")
    def test_claude_selected_mcp_uses_strict_project_config_and_tool_patterns(self, run):
        run.return_value = mock.Mock(returncode=0, stdout=json.dumps({"result": "{}"}), stderr="")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = root / ".mcp.json"
            config.write_text("{}", encoding="utf-8")
            ClaudeProvider().run(
                "x", root, tools=["Read"],
                mcp={
                    "selected": ["github"],
                    "unselected": ["other"],
                    "project_mcp_config": str(config),
                },
            )
        cmd = run.call_args.args[0]
        self.assertIn("--mcp-config", cmd)
        self.assertEqual(cmd[cmd.index("--mcp-config") + 1], str(config))
        self.assertIn("mcp__github__*", cmd)
        self.assertIn("--disallowedTools", cmd)
        self.assertIn("mcp__other__*", cmd)

    @mock.patch("factory.providers.subprocess.run")
    def test_codex_review_is_read_only(self, run):
        run.return_value = mock.Mock(returncode=0, stdout="{}", stderr="")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            install_profiles(root)
            CodexProvider().run("review", root, access="read-only")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--sandbox") + 1], "read-only")
        self.assertNotIn("--ask-for-approval", cmd)
        self.assertIn('default_permissions="aah_readonly"', cmd)

    def test_codex_extracts_nested_agent_message_from_jsonl(self):
        payload = "\n".join([
            json.dumps({"type": "thread.started"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"summary":"ok"}'}}),
            json.dumps({"type": "turn.completed"}),
        ])
        self.assertEqual(CodexProvider._agent_text(payload), '{"summary":"ok"}')

    def test_codex_turn_failed_raises(self):
        payload = json.dumps({"type": "turn.failed", "error": {"message": "boom"}})
        with self.assertRaises(ProviderError):
            CodexProvider._agent_text(payload)


class ProviderDiscoveryTests(unittest.TestCase):
    @mock.patch("factory.providers.shutil.which")
    @mock.patch("factory.providers.subprocess.run")
    def test_claude_auth_probe_is_subscription_first(self, run, which):
        which.side_effect = lambda name: f"/usr/bin/{name}" if name == "claude" else None
        def fake_run(cmd, **kwargs):
            if cmd == ["claude", "--version"]:
                return mock.Mock(returncode=0, stdout="Claude 1.0\n", stderr="")
            if cmd == ["claude", "auth", "status"]:
                self.assertNotIn("ANTHROPIC_API_KEY", kwargs["env"])
                self.assertNotIn("ANTHROPIC_AUTH_TOKEN", kwargs["env"])
                return mock.Mock(returncode=0, stdout="logged in", stderr="")
            raise AssertionError(cmd)
        run.side_effect = fake_run
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "paid", "ANTHROPIC_AUTH_TOKEN": "gateway"}, clear=False):
            providers = ProviderRegistry.discover()
        self.assertTrue(providers["claude"]["available"])
        self.assertTrue(providers["claude"]["authenticated"])
        self.assertEqual(providers["claude"]["auth"], "subscription_or_cli_managed")

    @mock.patch("factory.providers.shutil.which")
    @mock.patch("factory.providers.subprocess.run")
    def test_codex_unknown_status_command_is_not_false_negative(self, run, which):
        which.side_effect = lambda name: f"/usr/bin/{name}" if name == "codex" else None
        def fake_run(cmd, **kwargs):
            if cmd == ["codex", "--version"]:
                return mock.Mock(returncode=0, stdout="codex 1.0\n", stderr="")
            if cmd == ["codex", "login", "status"]:
                return mock.Mock(returncode=2, stdout="", stderr="error: unexpected argument status\nUsage: codex login")
            raise AssertionError(cmd)
        run.side_effect = fake_run
        providers = ProviderRegistry.discover()
        self.assertTrue(providers["codex"]["available"])
        self.assertIsNone(providers["codex"]["authenticated"])
        self.assertEqual(providers["codex"]["auth"], "status_probe_unavailable")


if __name__ == "__main__":
    unittest.main()
