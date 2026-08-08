import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory.artifacts import ArtifactStore
from factory.evidence import EvidenceStore, redact_data
from factory.final_gate import FinalGate
from factory.progress import ProgressDetector
from factory.project_adapter import ProjectAdapter
from factory.router import AdaptiveRouter
from factory.executor import ScriptedExecutor
from factory.profiles.lite import LiteRunner


class AuditRegressionTests(unittest.TestCase):
    def test_final_gate_never_passes_empty_or_malformed_rubric(self):
        with tempfile.TemporaryDirectory() as td:
            run=Path(td)
            self.assertFalse(FinalGate(run).evaluate([],[])["done"])
            self.assertFalse(FinalGate(run).evaluate({"unexpected":True},[])["done"])

    def test_string_evidence_ref_is_one_reference_and_false_evidence_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            run=Path(td); ev=EvidenceStore(run)
            ev.append({"id":"E-ok","type":"check","ok":True})
            rubric=[{"id":"R1","required":True,"status":"PASS","evidence_ref":"E-ok"}]
            self.assertTrue(FinalGate(run).evaluate(rubric,[])["done"])
            ev.append({"id":"E-bad","type":"bad-check","ok":False})
            rubric=[{"id":"R1","required":True,"status":"PASS","evidence":"E-bad"}]
            result=FinalGate(run).evaluate(rubric,[])
            self.assertFalse(result["done"])
            self.assertTrue(any("failed_evidence" in x for x in result["failures"]))

    def test_wrapped_findings_are_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            run=Path(td); EvidenceStore(run).append({"id":"E1","ok":True})
            rubric=[{"id":"R1","required":True,"status":"PASS","evidence":["E1"]}]
            findings={"findings":[{"id":"F1","severity":"major","status":"open"}]}
            self.assertFalse(FinalGate(run).evaluate(rubric,findings)["done"])

    def test_corrupt_evidence_fails_closed_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            run=Path(td); (run/"EVIDENCE.jsonl").write_text('{not json}\n')
            rubric=[{"id":"R1","required":True,"status":"PASS","evidence":["E1"]}]
            result=FinalGate(run).evaluate(rubric,[])
            self.assertFalse(result["done"])
            self.assertIn("evidence:invalid_jsonl",result["failures"])

    def test_structured_and_known_secret_values_are_redacted(self):
        secret="super-secret-value-123"
        with mock.patch.dict(os.environ,{"SERVICE_TOKEN":secret},clear=False):
            value=redact_data({
                "api_key":"raw-key",
                "detail":f"returned {secret}",
                "nested":{"password":"pw12345"},
            })
        text=json.dumps(value)
        self.assertNotIn(secret,text)
        self.assertNotIn("raw-key",text)
        self.assertNotIn("pw12345",text)
        self.assertIn("[REDACTED]",text)

    def test_progress_accepts_wrapped_rubric(self):
        score=ProgressDetector.score({"criteria":[{"id":"R1","required":True,"status":"PASS"}]})
        self.assertEqual(score,(1,1))

    def test_run_id_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            store=ArtifactStore(Path(td))
            with self.assertRaises(ValueError):
                store.create_run("x","lite","open","code",run_id="../../escape")
            with self.assertRaises(ValueError):
                store.get_run("../escape")

    def test_model_only_override_keeps_provider_and_unavailable_provider_fails(self):
        router=AdaptiveRouter({
            "claude":{"available":True,"authenticated":True},
            "codex":{"available":False,"authenticated":False},
        })
        assigned=router.assign_roles(["planner"],overrides={"planner":{"model":"opus"}})
        self.assertEqual(assigned["planner"]["provider"],"claude")
        self.assertEqual(assigned["planner"]["model"],"opus")
        with self.assertRaises(ValueError):
            router.assign_roles(["planner"],overrides={"planner":{"provider":"codex"}})

    def test_builder_cannot_overwrite_reserved_rubric(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)
            ex=ScriptedExecutor({})
            runner=LiteRunner(target,ex)
            run=runner._new("x","open","code")
            runner._ingest(run,{"_aah_role":"builder","artifacts":{"RUBRIC.json":[]},"evidence":[]})
            findings=runner._findings(run)
            self.assertTrue(any(str(f.get("id","")).startswith("F-POLICY-builder") for f in findings))

    def test_agent_artifact_secret_is_redacted_before_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); runner=LiteRunner(target,ScriptedExecutor({})); run=runner._new("x","open","code")
            with mock.patch.dict(os.environ,{"SERVICE_TOKEN":"do-not-store-this"},clear=False):
                runner._ingest(run,{"_aah_role":"planner","artifacts":{"SPEC.md":"token=do-not-store-this"},"evidence":[]})
            self.assertNotIn("do-not-store-this",(run.run_dir/"SPEC.md").read_text())

    def test_project_adapter_detects_linked_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"repo"; worktree=Path(td)/"wt"
            root.mkdir()
            if subprocess.run(["git","init",str(root)],capture_output=True).returncode!=0:
                self.skipTest("git unavailable")
            subprocess.run(["git","-C",str(root),"config","user.email","aah@test.local"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","AAH Test"],check=True)
            (root/"x.txt").write_text("x")
            subprocess.run(["git","-C",str(root),"add","x.txt"],check=True)
            subprocess.run(["git","-C",str(root),"commit","-m","init"],check=True,capture_output=True)
            subprocess.run(["git","-C",str(root),"worktree","add",str(worktree),"-b","test-wt"],check=True,capture_output=True)
            info=ProjectAdapter(worktree).inspect()["git"]
            self.assertTrue(info["is_repo"])
            self.assertTrue(info["is_linked_worktree"])


if __name__=="__main__":
    unittest.main()
