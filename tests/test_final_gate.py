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

    def test_pass_requires_real_evidence_and_no_major_findings(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"id":"E-1","kind":"test","ok":True,"detail":"ok"})
            rubric = [{"id":"R-1","status":"PASS","required":True,"evidence":["E-1"]}]
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertTrue(result["done"])
            result2 = FinalGate(run).evaluate(rubric, findings=[{"id":"F-1","severity":"major","status":"open"}])
            self.assertFalse(result2["done"])

if __name__ == "__main__": unittest.main()
