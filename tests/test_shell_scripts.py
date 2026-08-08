import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShellScriptTests(unittest.TestCase):
    def test_all_shipped_shell_scripts_parse(self):
        scripts = [
            ROOT / "install.sh",
            ROOT / "scripts" / "release-check.sh",
            ROOT / "scripts" / "provider-smoke.sh",
            ROOT / "scripts" / "sync-agents.sh",
        ]
        for script in scripts:
            with self.subTest(script=script.name):
                cp = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
                self.assertEqual(cp.returncode, 0, cp.stderr)

    def test_repository_contains_no_github_actions_workflows(self):
        workflows = ROOT / ".github" / "workflows"
        files = list(workflows.rglob("*")) if workflows.exists() else []
        self.assertEqual([path for path in files if path.is_file()], [])


if __name__ == "__main__":
    unittest.main()
