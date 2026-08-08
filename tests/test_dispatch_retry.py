import tempfile
import unittest
from pathlib import Path
from factory.profiles.lite import LiteRunner


class FlakyExecutor:
    def __init__(self, fail_twice=False):
        self.calls=[]; self.planner_attempts=0; self.fail_twice=fail_twice
    def execute(self, role, task, context, session=None):
        import uuid
        session=session or str(uuid.uuid4())
        self.calls.append({"role":role,"session":session,"task":task})
        if role=="planner":
            self.planner_attempts += 1
            if self.planner_attempts <= (2 if self.fail_twice else 1):
                raise RuntimeError("transient provider failure")
            return {"session":session,"artifacts":{
                "SPEC.md":"# SPEC\nBuild X\n",
                "RUBRIC.json":{"criteria":[{"id":"R-1","criterion":"X works","required":True}]},
            },"evidence":[]}
        if role=="builder":
            return {"session":session,"summary":"built","artifacts":{},"evidence":[]}
        if role=="evaluator":
            return {"session":session,"artifacts":{
                "RUBRIC_STATUS.json":{"criteria":[{"id":"R-1","status":"PASS","evidence":["E-1"]}]},
                "FINDINGS.json":[],
            },"evidence":[{"id":"E-1","type":"test","ok":True}]}
        raise AssertionError(role)


class DispatchRetryTests(unittest.TestCase):
    def test_first_failure_retries_with_fresh_session_then_continues(self):
        with tempfile.TemporaryDirectory() as td:
            executor=FlakyExecutor()
            result=LiteRunner(Path(td),executor).run("x",guardian="open")
            self.assertTrue(result["done"])
            planner_sessions=[c["session"] for c in executor.calls if c["role"]=="planner"]
            self.assertEqual(len(planner_sessions),2)
            self.assertNotEqual(planner_sessions[0],planner_sessions[1])

    def test_second_failure_aborts_instead_of_continuing(self):
        with tempfile.TemporaryDirectory() as td:
            executor=FlakyExecutor(fail_twice=True)
            result=LiteRunner(Path(td),executor).run("x",guardian="open")
            self.assertFalse(result["done"])
            self.assertEqual(result["state"]["status"],"failed")
            self.assertTrue(any("contract:missing" in item or "runtime" in item for item in result["gate"]["failures"]))
            self.assertEqual([c["role"] for c in executor.calls],["planner","planner"])


if __name__=="__main__":
    unittest.main()
