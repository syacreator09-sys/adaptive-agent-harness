import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from factory.evidence import EvidenceStore


class CLITests(unittest.TestCase):
    def run_cli(self, *args, cwd=None, env_patch=None):
        env = os.environ.copy()
        root = Path(__file__).resolve().parents[1]
        env["PYTHONPATH"] = str(root)
        if env_patch:
            env.update(env_patch)
        return subprocess.run(
            [sys.executable, "-m", "factory.cli", *args],
            cwd=cwd or root, env=env, text=True, capture_output=True,
        )

    def fake_claude(self, directory: Path):
        path = directory / "claude"
        path.write_text(
            "#!/usr/bin/env sh\n"
            "if [ \"${1:-}\" = \"--version\" ]; then echo 'Claude Code 1.0'; exit 0; fi\n"
            "if [ \"${1:-}\" = \"auth\" ] && [ \"${2:-}\" = \"status\" ]; then echo logged-in; exit 0; fi\n"
            "exit 0\n"
        )
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def test_setup_and_doctor_report_project_mcp_and_provider_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); project = root / "project"; project.mkdir()
            fake = root / "bin"; fake.mkdir(); self.fake_claude(fake)
            (project / "package.json").write_text('{"scripts":{"test":"echo ok"}}')
            (project / ".env.example").write_text("TOKEN=\n")
            (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"docs": {"command": "docs-server"}}}))
            path = str(fake) + os.pathsep + os.environ.get("PATH", "")
            setup = self.run_cli("setup", "--target", str(project), "--non-interactive", env_patch={"PATH": path})
            self.assertEqual(setup.returncode, 0, setup.stderr)
            doctor = self.run_cli("doctor", "--target", str(project), "--json", env_patch={"PATH": path})
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            payload = json.loads(doctor.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mcp"]["servers"][0]["name"], "docs")

    def test_doctor_fails_closed_when_no_provider_is_ready(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_cli(
                "doctor", "--target", td, "--json",
                env_patch={"PATH": "/usr/bin:/bin"},
            )
            payload = json.loads(result.stdout)
            if not any(info.get("available") for info in payload["providers"].values()):
                self.assertEqual(result.returncode, 3)
                self.assertFalse(payload["provider_ready"])

    def test_native_init_seal_gate_and_escalate(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            init = self.run_cli(
                "init-run", "build x", "--target", str(target), "--profile", "lite", "--json"
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            payload = json.loads(init.stdout); run_id = payload["run_id"]
            run_dir = target / ".aah" / "runs" / run_id
            (run_dir / "SPEC.md").write_text("# SPEC\nBuild X\n")
            (run_dir / "RUBRIC.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "criterion": "X works", "required": True}
            ]}))
            seal = self.run_cli("seal-rubric", run_id, "--target", str(target))
            self.assertEqual(seal.returncode, 0, seal.stderr)
            self.assertTrue((run_dir / "CONTRACT.json").exists())

            failed_gate = self.run_cli("gate", run_id, "--target", str(target))
            self.assertEqual(failed_gate.returncode, 2)
            self.assertIn("UNVERIFIED", failed_gate.stdout)

            EvidenceStore(run_dir).append({"id": "E-1", "type": "test", "ok": True})
            (run_dir / "RUBRIC_STATUS.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "status": "PASS", "evidence": ["E-1"]}
            ]}))
            passed_gate = self.run_cli("gate", run_id, "--target", str(target))
            self.assertEqual(passed_gate.returncode, 0, passed_gate.stderr)

            # Use a second incomplete run because completed runs do not need escalation.
            init2 = self.run_cli(
                "init-run", "build y", "--target", str(target), "--profile", "lite", "--json"
            )
            run2 = json.loads(init2.stdout)["run_id"]; run2dir = target / ".aah" / "runs" / run2
            (run2dir / "SPEC.md").write_text("# SPEC\nBuild Y\n")
            (run2dir / "RUBRIC.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "criterion": "Y works", "required": True}
            ]}))
            self.assertEqual(self.run_cli("seal-rubric", run2, "--target", str(target)).returncode, 0)
            child = self.run_cli("escalate", run2, "--to", "pro", "--target", str(target))
            self.assertEqual(child.returncode, 0, child.stderr)
            child_payload = json.loads(child.stdout)
            self.assertNotEqual(child_payload["run_id"], run2)
            self.assertFalse((Path(child_payload["run_dir"]) / "EVIDENCE.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
