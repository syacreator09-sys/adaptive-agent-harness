import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from factory.hook_guardian import main
from factory.guardian import Guardian, Decision


class HookGuardianTests(unittest.TestCase):
    def call(self, payload, mode="guarded"):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch.dict(
            os.environ, {"AAH_GUARDIAN_MODE": mode}, clear=False
        ), redirect_stdout(out):
            rc = main()
        return rc, json.loads(out.getvalue()) if out.getvalue().strip() else None

    def test_blocks_sensitive_and_outside_reads(self):
        _, data = self.call({"tool_name": "Read", "tool_input": {"file_path": "/tmp/project/.env"}, "cwd": "/tmp/project"})
        self.assertEqual(data["hookSpecificOutput"]["permissionDecision"], "deny")
        _, data2 = self.call({"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}, "cwd": "/tmp/project"})
        self.assertEqual(data2["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_locked_escalates_production_command(self):
        _, data = self.call(
            {"tool_name": "Bash", "tool_input": {"command": "kubectl apply -f prod.yaml"}, "cwd": "/tmp/project"},
            "locked",
        )
        self.assertEqual(data["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_grep_and_glob_sensitive_patterns_are_denied(self):
        _, grep = self.call({
            "agent_type": "aah-evaluator", "tool_name": "Grep",
            "tool_input": {"pattern": "token", "glob": "**/.env*", "path": "/tmp/project"}, "cwd": "/tmp/project",
        })
        self.assertEqual(grep["hookSpecificOutput"]["permissionDecision"], "deny")
        _, glob = self.call({
            "agent_type": "aah-evaluator", "tool_name": "Glob",
            "tool_input": {"pattern": "**/.ssh/**", "path": "/tmp/project"}, "cwd": "/tmp/project",
        })
        self.assertEqual(glob["hookSpecificOutput"]["permissionDecision"], "deny")


class NativeAgentRoleHookTests(unittest.TestCase):
    def call_role(self, payload, mode="guarded"):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch.dict(
            os.environ, {"AAH_GUARDIAN_MODE": mode}, clear=False
        ), redirect_stdout(out):
            rc = main()
        return rc, json.loads(out.getvalue()) if out.getvalue().strip() else None

    def test_planner_can_write_spec_but_builder_cannot_touch_contract(self):
        root = "/tmp/project"
        _, planner = self.call_role({
            "agent_type": "aah-planner", "tool_name": "Write",
            "tool_input": {"file_path": f"{root}/.aah/runs/RUN-1/SPEC.md"}, "cwd": root,
        })
        self.assertIsNone(planner)
        _, builder = self.call_role({
            "agent_type": "aah-builder", "tool_name": "Write",
            "tool_input": {"file_path": f"{root}/.aah/runs/RUN-1/CONTRACT.json"}, "cwd": root,
        })
        self.assertEqual(builder["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_evaluator_cannot_edit_product_but_can_write_owned_findings(self):
        root = "/tmp/project"
        _, denied = self.call_role({
            "agent_type": "aah-evaluator", "tool_name": "Write",
            "tool_input": {"file_path": f"{root}/src/app.py"}, "cwd": root,
        })
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        _, allowed = self.call_role({
            "agent_type": "aah-evaluator", "tool_name": "Write",
            "tool_input": {"file_path": f"{root}/.aah/runs/RUN-1/FINDINGS.json"}, "cwd": root,
        })
        self.assertIsNone(allowed)

    def test_evidence_log_is_runtime_owned_but_draft_and_ingest_are_allowed_for_verifier(self):
        root = "/tmp/project"
        _, log = self.call_role({
            "agent_type": "aah-evaluator", "tool_name": "Write",
            "tool_input": {"file_path": f"{root}/.aah/runs/RUN-1/EVIDENCE.jsonl"}, "cwd": root,
        })
        self.assertEqual(log["hookSpecificOutput"]["permissionDecision"], "deny")
        _, draft = self.call_role({
            "agent_type": "aah-evaluator", "tool_name": "Write",
            "tool_input": {"file_path": f"{root}/.aah/runs/RUN-1/EVIDENCE_DRAFT.json"}, "cwd": root,
        })
        self.assertIsNone(draft)
        command = ".aah/bin/factory evidence-ingest RUN-1 --file .aah/runs/RUN-1/EVIDENCE_DRAFT.json"
        _, ingest = self.call_role({
            "agent_type": "aah-evaluator", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": root,
        })
        self.assertIsNone(ingest)
        _, producer = self.call_role({
            "agent_type": "aah-builder", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": root,
        })
        self.assertEqual(producer["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_unscoped_grep_is_denied_for_review_brain(self):
        _, data = self.call_role({
            "agent_type": "aah-evaluator", "tool_name": "Grep",
            "tool_input": {"pattern": "TODO"}, "cwd": "/tmp/project",
        })
        self.assertEqual(data["hookSpecificOutput"]["permissionDecision"], "deny")


class DynamicGuardianModeTests(unittest.TestCase):
    def test_hook_uses_strictest_active_run_and_ignores_completed_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            done = root / ".aah" / "runs" / "RUN-1"; done.mkdir(parents=True)
            active = root / ".aah" / "runs" / "RUN-2"; active.mkdir(parents=True)
            (done / "STATE.json").write_text(json.dumps({"guardian": "locked", "status": "done"}))
            (active / "STATE.json").write_text(json.dumps({"guardian": "open", "status": "running"}))
            payload = {"tool_name": "Bash", "tool_input": {"command": "echo ok"}, "cwd": str(root)}
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch.dict(
                os.environ, {"AAH_TARGET_ROOT": str(root)}, clear=True
            ), redirect_stdout(out):
                rc = main()
            self.assertEqual(rc, 0)
            self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
