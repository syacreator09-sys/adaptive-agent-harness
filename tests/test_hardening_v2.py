import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from factory.artifacts import ArtifactStore
from factory.contracts import ContractError, seal_contract, verify_contract
from factory.evidence import EvidenceStore, redact_data
from factory.tool_adapter_cli import main as adapter_main


class ArtifactHardeningTests(unittest.TestCase):
    def test_run_id_and_artifact_path_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArtifactStore(Path(td))
            with self.assertRaises(ValueError):
                store.get_run("RUN-../escape")
            run = store.create_run("x", "lite", "open", "code")
            with self.assertRaises(ValueError):
                store.write_text(run.run_dir, "../../escape.txt", "bad")
            self.assertFalse((Path(td) / "escape.txt").exists())

    def test_create_run_allocates_distinct_ids(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArtifactStore(Path(td))
            first = store.create_run("a", "lite", "open", "code")
            second = store.create_run("b", "lite", "open", "code")
            self.assertNotEqual(first.run_id, second.run_id)
            self.assertTrue(first.run_dir.is_dir())
            self.assertTrue(second.run_dir.is_dir())


class ContractHardeningTests(unittest.TestCase):
    def seed(self, root: Path, rubric=None):
        (root / "SPEC.md").write_text("# SPEC\n\nBuild X\n\n", encoding="utf-8")
        (root / "RUBRIC.json").write_text(json.dumps(rubric or {"criteria": [
            {"id": "R-1", "criterion": "X works", "required": True}
        ]}), encoding="utf-8")

    def test_seal_normalizes_spec_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.seed(root)
            first = seal_contract(root)
            second = seal_contract(root)
            self.assertEqual(first, second)
            self.assertEqual((root / "SPEC.md").read_text(), "# SPEC\n\nBuild X\n")
            self.assertTrue(verify_contract(root)[0])

    def test_duplicate_rubric_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.seed(root, {"criteria": [
                {"id": "R-1", "criterion": "one"},
                {"id": "R-1", "criterion": "two"},
            ]})
            with self.assertRaises(ContractError):
                seal_contract(root)

    def test_contract_rejects_post_seal_baseline_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.seed(root); seal_contract(root)
            (root / "RUBRIC_BASELINE.json").write_text('{"criteria":[]}\n')
            ok, failures = verify_contract(root)
            self.assertFalse(ok)
            self.assertIn("contract:rubric_hash_mismatch", failures)


class EvidenceHardeningTests(unittest.TestCase):
    def test_audit_session_id_is_preserved_but_session_token_is_redacted(self):
        safe = redact_data({"session": "audit-123", "session_id": "audit-456", "session_token": "secret-token"})
        self.assertEqual(safe["session"], "audit-123")
        self.assertEqual(safe["session_id"], "audit-456")
        self.assertEqual(safe["session_token"], "[REDACTED]")

    def test_corrupt_evidence_row_is_returned_as_explicit_failure_record(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "EVIDENCE.jsonl").write_text("not-json\n")
            row = EvidenceStore(root).all()[0]
            self.assertTrue(row["_invalid"])
            self.assertFalse(row["ok"])


class ToolAdapterTests(unittest.TestCase):
    @mock.patch("factory.tool_adapter_cli.subprocess.run")
    def test_adapter_executes_without_shell_and_does_not_echo_config(self, run):
        run.return_value = mock.Mock(returncode=0)
        with mock.patch.dict(os.environ, {"AAH_TOOL_IMAGE": "image-wrapper --safe"}, clear=False):
            rc = adapter_main(["image", "input.png"])
        self.assertEqual(rc, 0)
        self.assertEqual(run.call_args.args[0], ["image-wrapper", "--safe", "input.png"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_unconfigured_adapter_fails_closed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(adapter_main(["video"]), 3)


if __name__ == "__main__":
    unittest.main()
