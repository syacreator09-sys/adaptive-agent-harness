import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fake_codex(bin_dir: Path):
    path = bin_dir / "codex"
    path.write_text(
        "#!/usr/bin/env sh\n"
        "if [ \"${1:-}\" = \"--version\" ]; then echo 'codex 1.0'; exit 0; fi\n"
        "if [ \"${1:-}\" = \"login\" ] && [ \"${2:-}\" = \"status\" ]; then echo logged-in; exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class InstallerTests(unittest.TestCase):
    def test_existing_project_is_preserved_and_safe_capabilities_are_generated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "project"; target.mkdir()
            fake_bin = root / "bin"; fake_bin.mkdir(); fake_codex(fake_bin)
            (target / "package.json").write_text('{"scripts":{"test":"echo ok"}}')
            (target / ".env").write_text("SECRET_TOKEN=super-secret\nPUBLIC_URL=https://example.test\n")
            (target / ".mcp.json").write_text(json.dumps({"mcpServers": {
                "github": {"type": "http", "url": "https://mcp.example", "headers": {"Authorization": "Bearer hidden-token"}}
            }}))
            (target / "AGENTS.md").write_text("# Existing rules\nKeep me.\n")
            settings = target / ".claude" / "settings.local.json"; settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({"hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo existing"}]}
            ]}}))
            codex = target / ".codex" / "config.toml"; codex.parent.mkdir(parents=True)
            codex.write_text('model = "custom"\n')
            env = os.environ.copy(); env["AAH_NO_GIT_INIT"] = "1"
            env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
            cp = subprocess.run(["bash", str(ROOT / "install.sh"), str(target)], env=env, text=True, capture_output=True)
            self.assertEqual(cp.returncode, 0, cp.stderr)

            project = json.loads((target / ".aah" / "project.json").read_text())
            capabilities = json.loads((target / ".aah" / "capabilities.json").read_text())
            self.assertIn("SECRET_TOKEN", project["env_names"])
            serialized = json.dumps({"project": project, "capabilities": capabilities})
            self.assertNotIn("super-secret", serialized)
            self.assertNotIn("hidden-token", serialized)
            self.assertEqual(project["mcp"]["servers"][0]["name"], "github")

            self.assertIn("Keep me.", (target / "AGENTS.md").read_text())
            merged = json.loads(settings.read_text())
            entries = merged["hooks"]["PreToolUse"]
            commands = [hook.get("command") for entry in entries for hook in entry.get("hooks", [])]
            self.assertIn("echo existing", commands)
            self.assertIn(".aah/bin/guardian-hook", commands)
            aah_entry = next(entry for entry in entries if any(h.get("command") == ".aah/bin/guardian-hook" for h in entry.get("hooks", [])))
            self.assertIn("Grep", aah_entry["matcher"])
            self.assertIn("Glob", aah_entry["matcher"])

            self.assertTrue((target / ".aah" / "bin" / "tool-adapter").exists())
            factory_text = (target / ".aah" / "bin" / "factory").read_text()
            for helper in ["evidence-ingest", "prepare-tasks", "task-gate"]:
                self.assertIn(helper, factory_text)
            self.assertTrue((target / ".claude" / "agents" / "aah-task-evaluator.md").exists())
            agent_text = (target / ".claude" / "agents" / "aah-evaluator.md").read_text()
            self.assertIn("Fresh context: **required", agent_text)
            self.assertIn("Recommended Claude class", agent_text)
            self.assertFalse((target / ".github" / "workflows").exists())

            codex_text = codex.read_text()
            self.assertIn('model = "custom"', codex_text)
            self.assertIn('[permissions.aah_readonly.filesystem]', codex_text)
            self.assertIn(':workspace_roots', codex_text)

    def test_new_target_directory_is_created(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "new-project"
            env = os.environ.copy(); env["AAH_NO_GIT_INIT"] = "1"
            # Keep the test independent from host Claude/Codex installations.
            env["PATH"] = "/usr/bin:/bin"
            cp = subprocess.run(["bash", str(ROOT / "install.sh"), str(target)], env=env, text=True, capture_output=True)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertTrue(target.is_dir())
            self.assertTrue((target / ".aah" / "bin" / "factory").exists())
            self.assertFalse((target / ".github" / "workflows").exists())

    def test_machine_without_codex_does_not_create_codex_config(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            env = os.environ.copy(); env["AAH_NO_GIT_INIT"] = "1"; env["PATH"] = "/usr/bin:/bin"
            cp = subprocess.run(["bash", str(ROOT / "install.sh"), str(target)], env=env, text=True, capture_output=True)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertFalse((target / ".codex" / "config.toml").exists())

    def test_malformed_claude_settings_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            settings = target / ".claude" / "settings.local.json"; settings.parent.mkdir(parents=True)
            original = "{ definitely-not-json "
            settings.write_text(original)
            env = os.environ.copy(); env["AAH_NO_GIT_INIT"] = "1"; env["PATH"] = "/usr/bin:/bin"
            cp = subprocess.run(["bash", str(ROOT / "install.sh"), str(target)], env=env, text=True, capture_output=True)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertEqual(settings.read_text(), original)
            self.assertIn("preserving unparseable", cp.stderr)


if __name__ == "__main__":
    unittest.main()
