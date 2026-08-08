import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CLITests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        env = os.environ.copy()
        root = Path(__file__).resolve().parents[1]
        env["PYTHONPATH"] = str(root)
        return subprocess.run([sys.executable, "-m", "factory.cli", *args], cwd=cwd or root, env=env, text=True, capture_output=True)

    def test_setup_and_doctor_existing_project(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "package.json").write_text('{"scripts":{"test":"echo ok"}}')
            (p / ".env.example").write_text('TOKEN=\n')
            r = self.run_cli("setup", "--target", str(p), "--non-interactive")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((p / ".aah" / "project.json").exists())
            d = self.run_cli("doctor", "--target", str(p), "--json")
            # Doctor is a health check: 0 when a provider is ready, 3 when no authenticated provider exists.
            self.assertIn(d.returncode, {0,3}, d.stderr)
            payload = json.loads(d.stdout)
            self.assertIn("providers", payload)
            self.assertIn("tools", payload)
            self.assertEqual(payload["ok"], d.returncode==0)


if __name__ == "__main__":
    unittest.main()
