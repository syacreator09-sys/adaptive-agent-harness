import json
import tempfile
import unittest
from pathlib import Path
from factory.artifacts import ArtifactStore
from factory.contracts import seal_contract
from factory.evidence import EvidenceStore
from factory.orchestrator import create_escalation_child


class EscalationTests(unittest.TestCase):
    def test_child_inherits_contract_inputs_and_findings_but_not_old_proof(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td); store = ArtifactStore(target)
            parent = store.create_run("build x", "lite", "guarded", "code")
            (parent.run_dir / "SPEC.md").write_text("# SPEC\nBuild X\n")
            (parent.run_dir / "RUBRIC.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "criterion": "works", "required": True}
            ]}))
            seal_contract(parent.run_dir)
            (parent.run_dir / "RUBRIC_STATUS.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "status": "FAIL", "evidence": ["E-1"]}
            ]}))
            (parent.run_dir / "FINDINGS.json").write_text(json.dumps([
                {"id": "F-1", "severity": "major", "status": "open", "rubric_id": "R-1"}
            ]))
            EvidenceStore(parent.run_dir).append({"id": "E-1", "type": "test", "ok": False})

            child = create_escalation_child(target, parent.run_id, "pro", failures=["R-1:status=FAIL"])
            self.assertNotEqual(child.run_id, parent.run_id)
            self.assertTrue((child.run_dir / "SPEC.md").exists())
            self.assertTrue((child.run_dir / "RUBRIC.json").exists())
            self.assertTrue((child.run_dir / "FINDINGS.json").exists())
            self.assertFalse((child.run_dir / "EVIDENCE.jsonl").exists())
            self.assertFalse((child.run_dir / "RUBRIC_STATUS.json").exists())
            self.assertFalse((child.run_dir / "CONTRACT.json").exists())
            context = json.loads((child.run_dir / "ESCALATION_CONTEXT.json").read_text())
            self.assertFalse(context["evidence_inherited_as_proof"])
            self.assertTrue(context["fresh_child_run"])
            seal_contract(child.run_dir)
            self.assertTrue((child.run_dir / "CONTRACT.json").exists())

    def test_escalation_cannot_move_sideways_or_down(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td); store = ArtifactStore(target)
            parent = store.create_run("x", "pro", "guarded", "code")
            with self.assertRaises(ValueError):
                create_escalation_child(target, parent.run_id, "pro")


if __name__ == "__main__":
    unittest.main()
