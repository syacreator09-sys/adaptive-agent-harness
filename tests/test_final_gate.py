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

    def test_pass_requires_explicit_positive_evidence(self):
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

    def test_negative_evidence_blocks_even_if_same_reference_has_positive_record(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            store = EvidenceStore(run)
            store.append({"id": "E-shared", "type": "test", "ok": True})
            store.append({"id": "E-shared", "type": "test", "ok": False})
            status(run, "PASS", ["E-shared"])
            result = FinalGate(run).evaluate(None, [])
            self.assertFalse(result["done"])
            self.assertIn("R-1:failed_evidence:E-shared", result["failures"])

    def test_type_reference_is_valid_only_when_explicitly_positive(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td); sealed_run(run)
            EvidenceStore(run).append({"id": "E-1", "type": "unittest_run", "ok": True})
            (run / "RUBRIC_STATUS.json").write_text(json.dumps({"criteria": [
                {"id": "R-1", "status": "PASS", "evidence_ref": ["unittest_run"]}
            ]}), encoding="utf-8")
            self.assertTrue(FinalGate(run).evaluate(None, [])["done"])

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
