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

    def test_rubric_wrapped_in_criteria_dict_does_not_crash(self):
        """Real bug found live (plan AUTONOMÍA TOTAL, 2026-08-07,
        RUN-20260807-004): a real evaluator wrote RUBRIC.json as
        {"criteria": [...]} instead of a bare list -- `for item in rubric`
        iterated the dict's string keys and crashed with AttributeError
        on item.get(...), killing the whole run before FINAL_REPORT was
        ever written."""
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

    def test_findings_written_as_a_free_form_report_object_does_not_crash(self):
        """Real bug found live (plan AUTONOMÍA TOTAL, 2026-08-07,
        RUN-20260807-006): a real evaluator wrote FINDINGS.json as one
        free-form report dict (root_cause/notes/verdict/...) with no
        "findings" list at all -- `for f in findings` iterated the
        dict's string keys and crashed with AttributeError, same class
        as the RUBRIC.json crash fixed above. Must degrade to "no
        additional findings" instead."""
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"id":"E-1","kind":"test","ok":True,"detail":"ok"})
            rubric = [{"id":"R-1","status":"PASS","required":True,"evidence":["E-1"]}]
            findings = {"root_cause":"off-by-one","verdict":"PASS","notes":["fine"]}
            result = FinalGate(run).evaluate(rubric, findings)
            self.assertTrue(result["done"])

    def test_evidence_ref_key_and_type_based_reference_are_admissible(self):
        """A real evaluator referenced evidence by its record "type"
        (e.g. "unittest_run") under the key "evidence_ref", not by the
        EvidenceStore's own auto-derived "id" under "evidence" -- neither
        agents.py nor the .claude/agents/*.md contracts pin the exact
        field name or reference scheme, and the type-based reference
        does resolve to a real, admissible EVIDENCE.jsonl record."""
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"kind":"test","type":"unittest_run","detail":"OK"})
            rubric = [{"id":"R-1","status":"PASS","required":True,"evidence_ref":["unittest_run"]}]
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertTrue(result["done"])

    def test_evidence_refs_plural_key_is_also_admissible(self):
        """A third real evaluator (RUN-20260807-007) used "evidence_refs"
        (plural) -- a third distinct field name for the same concept,
        none of the three ("evidence", "evidence_ref", "evidence_refs")
        pinned anywhere in agents.py or .claude/agents/*.md."""
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"id":"EV-01","kind":"test","detail":"ok"})
            rubric = [{"id":"R-1","status":"PASS","required":True,"evidence_refs":["EV-01"]}]
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertTrue(result["done"])

    def test_empty_rubric_never_vacuously_passes(self):
        """Real bug found live (plan AUTONOMÍA TOTAL, 2026-08-07,
        RUN-20260807-009): a run wrote no RUBRIC.json/FINDINGS.json/
        EVIDENCE at all and still closed done=true after one pass,
        because zero criteria produced zero failures. A silent false
        positive -- absence of verification must never read as PASS."""
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            result = FinalGate(run).evaluate([], findings=[])
            self.assertFalse(result["done"])
            self.assertIn("rubric:no_criteria_recorded", result["failures"])

    def test_verdict_key_and_evidence_ids_key_are_also_admissible(self):
        """A fourth real evaluator (RUN-20260807-008) used "verdict"
        instead of "status" AND "evidence_ids" instead of any of the
        three evidence-key variants already covered -- confirming this
        is a genuinely recurring schema-drift problem, not a one-off."""
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            ev = EvidenceStore(run)
            ev.append({"id":"ev3-05","kind":"test","detail":"ok"})
            rubric = [{"id":"C1","required":True,"verdict":"PASS","evidence_ids":["ev3-05"]}]
            result = FinalGate(run).evaluate(rubric, findings=[])
            self.assertTrue(result["done"])

if __name__ == "__main__": unittest.main()
