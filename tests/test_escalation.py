import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from factory.artifacts import ArtifactStore
from factory.cli import escalate_cmd, seal_rubric_cmd
from factory.evidence import EvidenceStore


class EscalationTests(unittest.TestCase):
    def test_lite_to_pro_creates_fresh_child_with_artifact_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); store=ArtifactStore(target)
            parent=store.create_run("build x","lite","guarded","code")
            store.write_json(parent.run_dir,"RUBRIC.json",[{"id":"R1","required":True,"status":"FAIL","evidence":["E1"]}])
            store.write_json(parent.run_dir,"FINDINGS.json",[{"id":"F1","severity":"major","status":"open"}])
            store.write_json(parent.run_dir,"FINAL_REPORT.json",{"done":False})
            state=store.read_json(parent.run_dir,"STATE.json",{}); state.update({"phase":"paused","status":"incomplete","escalation":"pro"}); store.write_json(parent.run_dir,"STATE.json",state)
            out=io.StringIO()
            with redirect_stdout(out):
                rc=escalate_cmd(SimpleNamespace(target=str(target),run_id=parent.run_id,profile="pro",json=True))
            self.assertEqual(rc,0)
            payload=json.loads(out.getvalue())
            self.assertNotEqual(payload["run_id"],parent.run_id)
            child=store.get_run(payload["run_id"])
            req=store.read_json(child.run_dir,"REQUEST.json",{})
            self.assertEqual(req["profile"],"pro")
            self.assertEqual(req["parent_run_id"],parent.run_id)
            handoff=store.read_json(child.run_dir,"ESCALATION_CONTEXT.json",{})
            self.assertEqual(handoff["parent_profile"],"lite")
            self.assertEqual(handoff["findings"][0]["id"],"F1")
            parent_state=store.read_json(parent.run_dir,"STATE.json",{})
            self.assertEqual(parent_state["child_run_id"],child.run_id)
            self.assertEqual(parent_state["status"],"incomplete")

    def test_escalation_must_move_up(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); store=ArtifactStore(target); parent=store.create_run("x","pro","guarded","code")
            err=io.StringIO()
            with redirect_stderr(err):
                rc=escalate_cmd(SimpleNamespace(target=str(target),run_id=parent.run_id,profile="pro",json=False))
            self.assertEqual(rc,2)
            self.assertIn("Invalid escalation",err.getvalue())


class RubricSealTests(unittest.TestCase):
    def test_seal_rubric_creates_runtime_owned_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); store=ArtifactStore(target); run=store.create_run("x","lite","open","code")
            rubric=[{"id":"R1","description":"works","required":True,"status":"UNVERIFIED","evidence":[]}]
            store.write_json(run.run_dir,"RUBRIC.json",rubric)
            out=io.StringIO()
            with redirect_stdout(out):
                rc=seal_rubric_cmd(SimpleNamespace(target=str(target),run_id=run.run_id))
            self.assertEqual(rc,0)
            self.assertEqual(store.read_json(run.run_dir,"RUBRIC_BASELINE.json",None),rubric)

    def test_late_rubric_seal_is_refused_after_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); store=ArtifactStore(target); run=store.create_run("x","lite","open","code")
            store.write_json(run.run_dir,"RUBRIC.json",[{"id":"R1","required":True,"status":"UNVERIFIED"}])
            EvidenceStore(run.run_dir).append({"id":"E1","type":"check","ok":True})
            err=io.StringIO()
            with redirect_stderr(err):
                rc=seal_rubric_cmd(SimpleNamespace(target=str(target),run_id=run.run_id))
            self.assertEqual(rc,2)
            self.assertFalse((run.run_dir/"RUBRIC_BASELINE.json").exists())


if __name__=="__main__":
    unittest.main()
