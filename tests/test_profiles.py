import tempfile
import unittest
from pathlib import Path
from factory.executor import ScriptedExecutor
from factory.profiles.lite import LiteRunner
from factory.profiles.pro import ProRunner
from factory.profiles.factory import FactoryRunner


def planner_ok():
    return {"artifacts": {
        "SPEC.md": "# SPEC\n\n## Objective\nBuild X\n",
        "RUBRIC.json": {"criteria": [
            {"id": "R-1", "criterion": "X works", "required": True}
        ]},
        "PLANNING_REPORT.md": "planned",
    }}


def evaluator_fail(evidence_id="E-1"):
    return {
        "artifacts": {
            "RUBRIC_STATUS.json": {"criteria": [
                {"id": "R-1", "status": "FAIL", "evidence": [evidence_id]}
            ]},
            "FINDINGS.json": [
                {"id": "F-1", "severity": "major", "status": "open", "rubric_id": "R-1"}
            ],
            "FINDINGS.md": "# Findings\n- F-1 major",
        },
        "evidence": [{"id": evidence_id, "type": "test", "ok": False, "detail": "failed"}],
    }


def evaluator_pass(evidence_id="E-2"):
    return {
        "artifacts": {
            "RUBRIC_STATUS.json": {"criteria": [
                {"id": "R-1", "status": "PASS", "evidence": [evidence_id]}
            ]},
            "FINDINGS.json": [
                {"id": "F-1", "severity": "major", "status": "resolved", "rubric_id": "R-1"}
            ],
        },
        "evidence": [{"id": evidence_id, "type": "test", "ok": True, "detail": "passed"}],
    }


def task_eval(task_id, evidence_id):
    criterion_id = f"{task_id}-R-001"
    return {
        "artifacts": {
            "TASK_RUBRIC_STATUS.json": {"criteria": [
                {"id": criterion_id, "status": "PASS", "evidence": [evidence_id]}
            ]},
            "TASK_FINDINGS.json": [],
        },
        "evidence": [{
            "id": evidence_id,
            "type": "task_verification",
            "task_id": task_id,
            "ok": True,
            "detail": "task acceptance verified",
        }],
        "task_result": {"status": "PASS"},
    }


class ProfileTests(unittest.TestCase):
    def test_lite_keeps_three_roles_and_uses_fresh_evaluator_each_pass(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            ex = ScriptedExecutor({
                "planner": [planner_ok()],
                "builder": [{"summary": "built"}, {"summary": "fixed"}],
                "evaluator": [evaluator_fail(), evaluator_pass()],
            })
            out = LiteRunner(target, ex).run("build x", guardian="open")
            self.assertTrue(out["done"])
            roles = [call["role"] for call in ex.calls]
            self.assertEqual(roles, ["planner", "builder", "evaluator", "builder", "evaluator"])
            evaluator_sessions = [call["session"] for call in ex.calls if call["role"] == "evaluator"]
            self.assertEqual(len(evaluator_sessions), 2)
            self.assertEqual(len(set(evaluator_sessions)), 2)
            run_dir = target / ".aah" / "runs" / out["run_id"]
            self.assertTrue((run_dir / "CONTRACT.json").exists())
            self.assertTrue((run_dir / "RUBRIC_BASELINE.json").exists())
            self.assertTrue((run_dir / "EVENTS.jsonl").exists())

    def test_pro_adds_architect_tester_and_fixer_but_keeps_fresh_evaluation(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            ex = ScriptedExecutor({
                "planner": [planner_ok()],
                "architect": [{"artifacts": {"ARCHITECTURE.md": "# Architecture\n"}}],
                "builder": [{"summary": "built"}],
                "tester": [
                    {"evidence": [{"id": "T-1", "type": "technical_test", "ok": True, "detail": "suite"}]},
                    {"evidence": [{"id": "T-2", "type": "technical_test", "ok": True, "detail": "suite2"}]},
                ],
                "evaluator": [evaluator_fail(), evaluator_pass()],
                "fixer": [{"summary": "fixed"}],
            })
            out = ProRunner(target, ex).run("build x", guardian="guarded")
            self.assertTrue(out["done"])
            roles = [call["role"] for call in ex.calls]
            self.assertIn("architect", roles)
            self.assertEqual(roles.count("tester"), 2)
            self.assertEqual(roles.count("fixer"), 1)
            sessions = [call["session"] for call in ex.calls if call["role"] == "evaluator"]
            self.assertEqual(len(sessions), len(set(sessions)))

    def test_factory_uses_sealed_mini_harness_for_every_task_before_integration(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            task_graph = {"tasks": [
                {
                    "id": "T1", "title": "backend", "profile": "lite", "depends_on": [],
                    "acceptance": ["backend returns expected result"], "scope": ["backend/**"],
                },
                {
                    "id": "T2", "title": "frontend", "profile": "lite", "depends_on": ["T1"],
                    "acceptance": ["frontend consumes backend"], "scope": ["frontend/**"],
                },
            ]}
            ex = ScriptedExecutor({
                "planner": [planner_ok()],
                "architect": [{"artifacts": {"ARCHITECTURE.md": "# Architecture\n", "TASKS.json": task_graph}}],
                "worker": [{"summary": "t1"}, {"summary": "t2"}],
                "task_evaluator": [task_eval("T1", "TE-1"), task_eval("T2", "TE-2")],
                "integrator": [{"artifacts": {"INTEGRATION_REPORT.md": "integrated"}}],
                "system_tester": [{"evidence": [
                    {"id": "SYS-1", "type": "system_test", "ok": True, "detail": "system"}
                ]}],
                "evaluator": [evaluator_pass("E-GLOBAL")],
                "security_reviewer": [{"evidence": [
                    {"id": "SEC-1", "type": "security", "ok": True, "detail": "secure"}
                ]}],
                "final_reviewer": [{"artifacts": {"REVIEW_REPORT.md": "reviewed"}}],
            })
            out = FactoryRunner(target, ex).run("big system", guardian="guarded")
            self.assertTrue(out["done"])
            worker_calls = [call for call in ex.calls if call["role"] == "worker"]
            self.assertEqual([call["task"]["id"] for call in worker_calls], ["T1", "T2"])
            task_eval_sessions = [call["session"] for call in ex.calls if call["role"] == "task_evaluator"]
            self.assertEqual(len(task_eval_sessions), len(set(task_eval_sessions)))
            run_dir = target / ".aah" / "runs" / out["run_id"]
            for task_id in ["T1", "T2"]:
                self.assertTrue((run_dir / "tasks" / task_id / "CONTRACT.json").exists())
                self.assertTrue((run_dir / "tasks" / task_id / "RUBRIC_BASELINE.json").exists())
            integration_index = next(i for i, call in enumerate(ex.calls) if call["role"] == "integrator")
            last_task_eval_index = max(i for i, call in enumerate(ex.calls) if call["role"] == "task_evaluator")
            self.assertGreater(integration_index, last_task_eval_index)


if __name__ == "__main__":
    unittest.main()
