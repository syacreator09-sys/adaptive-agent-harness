import json
import tempfile
import unittest
from pathlib import Path
from factory.contracts import seal_contract
from factory.final_gate import FinalGate
from factory.evidence import EvidenceStore


def sealed_run(path: Path):
    (path / "SPEC.md").write_text("# SPEC\n\nBuild X\n", encoding="utf-8")
    (path / "RUBRIC.json").write_text(json.dumps({"criteria": [
        {"id": "R-1", "criterion": "X works", "required": True}
    ]}), encoding="utf-8")
    seal_contract(path)


def status(path: Path, value: str, evidence):
    (path / "RUBRIC_STATUS.json").write_text(json.dumps({"criteria": [
        {"id": "R-1", "status": value, "evidence": evidence}
    ]}), encoding="utf-8")


class FinalGateTests(unittest.TestCase):
    def test_unsealed_run_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            result = FinalGate(Path(td)).evaluate([], [])
            self.assertFalse(result["done"])
            self.assertIn("contract:missing", result["failures"])

    def test_unverified_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "test", "ok": True})
            status(run, "UNVERIFIED", ["E-1"])
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("R-1:status=UNVERIFIED", result["failures"])

    def test_pass_requires_explicit_positive_evidence_id(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "test", "ok": True, "detail": "executed"})
            status(run, "PASS", ["E-1"])
            result = FinalGate(run).evaluate(None, [])
            self.assertTrue(result["done"])
            self.assertEqual(result["passed"], 1)

    def test_narrative_evidence_without_ok_cannot_support_pass(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "test", "detail": "looks good"})
            status(run, "PASS", ["E-1"])
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertEqual(result["passed"], 0)
            self.assertIn("R-1:unverified_evidence:E-1", result["failures"])

    def test_duplicate_evidence_id_is_ambiguous_and_blocks_pass(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            store = EvidenceStore(run)
            store.append({"id": "E-shared", "type": "test", "ok": True})
            store.append({"id": "E-shared", "type": "test", "ok": False})
            status(run, "PASS", ["E-shared"])
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("evidence:duplicate_id:E-shared", result["failures"])
            self.assertIn("R-1:ambiguous_evidence:E-shared", result["failures"])

    def test_semantic_type_cannot_substitute_for_stable_evidence_id(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "unittest_run", "ok": True})
            status(run, "PASS", ["unittest_run"])
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("R-1:invalid_evidence:unittest_run", result["failures"])

    def test_duplicate_status_id_is_rejected_instead_of_last_write_winning(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "test", "ok": True})
            (run / "RUBRIC_STATUS.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "status": "FAIL", "evidence": []},
                {"id": "R-1", "status": "PASS", "evidence": ["E-1"]},
            ]}), encoding="utf-8")
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("status:duplicate_id:R-1", result["failures"])

    def test_unknown_status_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "test", "ok": True})
            (run / "RUBRIC_STATUS.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "status": "PASS", "evidence": ["E-1"]},
                {"id": "R-INVENTED", "status": "PASS", "evidence": ["E-1"]},
            ]}), encoding="utf-8")
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("status:unknown_id:R-INVENTED", result["failures"])

    def test_open_major_finding_blocks_pass(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "test", "ok": True})
            status(run, "PASS", ["E-1"])
            result = FinalGate(run).evaluate(None, [
                {"id": "F-1", "severity": "major", "status": "open"}
            ])
            self.assertFalse(result["done"])
            self.assertIn("F-1:open_major", result["failures"])

    def test_contract_tampering_blocks_pass(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "test", "ok": True})
            status(run, "PASS", ["E-1"])
            (run / "SPEC.md").write_text("# changed after seal\n", encoding="utf-8")
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("contract:spec_hash_mismatch", result["failures"])

    def test_corrupt_evidence_jsonl_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            (run / "EVIDENCE.jsonl").write_text("{not json}\n", encoding="utf-8")
            status(run, "PASS", ["E-1"])
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("evidence:invalid_jsonl", result["failures"])


if __name__ == "__main__":
    unittest.main()
