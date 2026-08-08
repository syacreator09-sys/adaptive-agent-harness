import tempfile
import unittest
from pathlib import Path
from factory.final_gate import FinalGate
from factory.evidence import EvidenceStore


class FinalGateTests(unittest.TestCase):
    def test_unverified_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"id":"E-1","kind":"test","ok":True,"detail":"ok"})
            rubric = [{"id":"R-1","status":"UNVERIFIED","required":True,"evidence":["E-1"]}]
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertFalse(result["done"])

    def test_pass_requires_real_positive_evidence_and_no_major_findings(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"id":"E-1","kind":"test","ok":True,"detail":"ok"})
            rubric = [{"id":"R-1","status":"PASS","required":True,"evidence":["E-1"]}]
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertTrue(result["done"])
            result2 = FinalGate(run).evaluate(rubric, findings=[{"id":"F-1","severity":"major","status":"open"}])
            self.assertFalse(result2["done"])

    def test_rubric_wrapped_in_criteria_dict_does_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"id":"E-1","kind":"test","ok":True,"detail":"ok"})
            rubric = {"criteria": [{"id":"R-1","status":"PASS","required":True,"evidence":["E-1"]}], "overall_verdict":"PASS"}
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertTrue(result["done"])

    def test_non_dict_rubric_item_is_unverified_not_a_crash(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            result = FinalGate(run).evaluate(["R-1"], findings=[])
            self.assertFalse(result["done"])
            self.assertIn("R-1:status=UNVERIFIED", result["failures"])

    def test_evidence_ref_key_and_type_based_reference_are_admissible_when_positive(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"kind":"test","type":"unittest_run","ok":True,"detail":"OK"})
            rubric = [{"id":"R-1","status":"PASS","required":True,"evidence_ref":["unittest_run"]}]
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertTrue(result["done"])

    def test_narrative_evidence_without_ok_never_supports_pass(self):
        with tempfile.TemporaryDirectory() as td:
            run=Path(td)
            EvidenceStore(run).append({"id":"E-1","detail":"looks good"})
            rubric=[{"id":"R-1","status":"PASS","required":True,"evidence":["E-1"]}]
            result=FinalGate(run).evaluate(rubric,[])
            self.assertFalse(result["done"])
            self.assertIn("R-1:unverified_evidence:E-1",result["failures"])

    def test_empty_or_all_optional_rubric_never_completes(self):
        with tempfile.TemporaryDirectory() as td:
            run=Path(td)
            self.assertFalse(FinalGate(run).evaluate([],[])["done"])
            optional=[{"id":"R-opt","required":False,"status":"PASS","evidence":[]}]
            self.assertFalse(FinalGate(run).evaluate(optional,[])["done"])


if __name__ == "__main__":
    unittest.main()
