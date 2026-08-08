import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from factory.artifacts import ArtifactStore
from factory.contracts import seal_contract
from factory.evidence import EvidenceStore
from factory.evidence_ingest_cli import main


class EvidenceIngestTests(unittest.TestCase):
    def make_run(self, target: Path):
        run = ArtifactStore(target).create_run("x", "lite", "guarded", "code")
        (run.run_dir / "SPEC.md").write_text("# SPEC\nBuild X\n")
        (run.run_dir / "RUBRIC.json").write_text(json.dumps({"criteria": [
            {"id": "R-1", "criterion": "works", "required": True}
        ]}))
        seal_contract(run.run_dir)
        return run

    def test_ingest_appends_redacted_evidence_and_removes_draft(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td); run = self.make_run(target)
            draft = run.run_dir / "EVIDENCE_DRAFT.json"
            draft.write_text(json.dumps({
                "id": "E-1", "type": "test", "ok": True,
                "api_key": "do-not-store", "detail": "ok",
            }))
            with mock.patch.dict(os.environ, {"AAH_TARGET_ROOT": str(target)}, clear=False):
                rc = main([run.run_id, "--file", str(draft)])
            self.assertEqual(rc, 0)
            self.assertFalse(draft.exists())
            rows = EvidenceStore(run.run_dir).all()
            self.assertEqual(rows[0]["id"], "E-1")
            self.assertEqual(rows[0]["api_key"], "[REDACTED]")

    def test_ingest_rejects_draft_outside_run(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td); run = self.make_run(target)
            outside = target / "EVIDENCE_DRAFT.json"; outside.write_text("{}")
            with mock.patch.dict(os.environ, {"AAH_TARGET_ROOT": str(target)}, clear=False):
                rc = main([run.run_id, "--file", str(outside)])
            self.assertEqual(rc, 2)
            self.assertTrue(outside.exists())

    def test_task_evidence_goes_to_task_local_store(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td); run = self.make_run(target)
            task = run.run_dir / "tasks" / "T1"; task.mkdir(parents=True)
            (task / "SPEC.md").write_text("# task\n")
            (task / "RUBRIC.json").write_text(json.dumps({"criteria": [
                {"id": "T1-R-001", "criterion": "task works", "required": True}
            ]}))
            seal_contract(task)
            draft = task / "EVIDENCE_DRAFT.json"
            draft.write_text(json.dumps([{"id": "TE-1", "type": "task_verification", "ok": True}]))
            with mock.patch.dict(os.environ, {"AAH_TARGET_ROOT": str(target)}, clear=False):
                rc = main([run.run_id, "--file", str(draft)])
            self.assertEqual(rc, 0)
            self.assertEqual(EvidenceStore(task).all()[0]["id"], "TE-1")
            self.assertFalse((run.run_dir / "EVIDENCE.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
