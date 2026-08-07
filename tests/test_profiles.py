import tempfile
import unittest
from pathlib import Path
from factory.artifacts import ArtifactStore
from factory.executor import ScriptedExecutor
from factory.profiles.lite import LiteRunner
from factory.profiles.pro import ProRunner
from factory.profiles.factory import FactoryRunner


def planner_ok():
    return {"artifacts": {
        "SPEC.md": "# Spec\nBuild X",
        "RUBRIC.json": [{"id":"R-1","description":"works","required":True,"status":"UNVERIFIED","evidence":[]}]
    }}

def evaluator_fail():
    return {"artifacts": {
        "RUBRIC.json": [{"id":"R-1","description":"works","required":True,"status":"FAIL","evidence":["E-1"]}],
        "FINDINGS.json": [{"id":"F-1","severity":"major","status":"open","rubric_id":"R-1"}]
    }, "evidence":[{"id":"E-1","kind":"test","ok":False,"detail":"failed"}]}

def evaluator_pass():
    return {"artifacts": {
        "RUBRIC.json": [{"id":"R-1","description":"works","required":True,"status":"PASS","evidence":["E-2"]}],
        "FINDINGS.json": [{"id":"F-1","severity":"major","status":"resolved","rubric_id":"R-1"}]
    }, "evidence":[{"id":"E-2","kind":"test","ok":True,"detail":"passed"}]}

class ProfileTests(unittest.TestCase):
    def test_lite_loops_and_uses_fresh_evaluator(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            ex = ScriptedExecutor({
                "planner":[planner_ok()],
                "builder":[{"summary":"built"},{"summary":"fixed"}],
                "evaluator":[evaluator_fail(), evaluator_pass()],
            })
            out = LiteRunner(target, ex).run("build x", guardian="open")
            self.assertTrue(out["done"])
            sessions = [x["session"] for x in ex.calls if x["role"] == "evaluator"]
            self.assertEqual(len(set(sessions)), 2)

    def test_pro_has_architect_tester_and_fixer(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            ex = ScriptedExecutor({
                "planner":[planner_ok()],
                "architect":[{"artifacts":{"ARCHITECTURE.md":"arch"}}],
                "builder":[{"summary":"built"}],
                "tester":[{"evidence":[{"id":"T-1","kind":"test","ok":True,"detail":"suite"}]} , {"evidence":[{"id":"T-2","kind":"test","ok":True,"detail":"suite2"}]}],
                "evaluator":[evaluator_fail(), evaluator_pass()],
                "fixer":[{"summary":"fixed"}],
            })
            out = ProRunner(target, ex).run("build x", guardian="guarded")
            self.assertTrue(out["done"])
            roles = [c["role"] for c in ex.calls]
            self.assertIn("architect", roles); self.assertIn("tester", roles); self.assertIn("fixer", roles)

    def test_factory_validates_task_graph_and_system_gates(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            task_graph = {"tasks":[
                {"id":"T1","title":"backend","profile":"lite","depends_on":[]},
                {"id":"T2","title":"frontend","profile":"lite","depends_on":["T1"]}
            ]}
            ex = ScriptedExecutor({
                "planner":[planner_ok()],
                "architect":[{"artifacts":{"ARCHITECTURE.md":"arch","TASKS.json":task_graph}}],
                "worker":[{"summary":"t1"},{"summary":"t2"}],
                "task_evaluator":[{"task_result":{"status":"PASS"}},{"task_result":{"status":"PASS"}}],
                "integrator":[{"summary":"integrated"}],
                "system_tester":[{"evidence":[{"id":"SYS-1","kind":"test","ok":True,"detail":"system"}]}],
                "evaluator":[evaluator_pass()],
                "security_reviewer":[{"evidence":[{"id":"SEC-1","kind":"security","ok":True,"detail":"secure"}]}],
                "final_reviewer":[{"summary":"reviewed"}],
            })
            out = FactoryRunner(target, ex).run("big system", guardian="guarded")
            self.assertTrue(out["done"])
            worker_calls = [c for c in ex.calls if c["role"] == "worker"]
            self.assertEqual([c["task"]["id"] for c in worker_calls], ["T1","T2"])
            task_eval_sessions=[c["session"] for c in ex.calls if c["role"]=="task_evaluator"]
            self.assertEqual(len(task_eval_sessions),len(set(task_eval_sessions)))

if __name__ == "__main__": unittest.main()
