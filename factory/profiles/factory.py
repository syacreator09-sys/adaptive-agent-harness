from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from ..models import Phase
from ..domains import role_for
from ..taskgraph import TaskGraph, TaskGraphError
from ..contracts import seal_contract, baseline_criteria, status_map
from ..evidence import EvidenceStore, redact_data
from ..events import EventJournal
from ..final_gate import FinalGate, normalize_findings
from ..gitops import GitCheckpoints
from .common import BaseRunner, AgentDispatchError


class FactoryRunner(BaseRunner):
    profile = "factory"

    @staticmethod
    def _explicit_evidence_gate(result: dict[str, Any], name: str) -> dict[str, Any]:
        evidence = [item for item in (result.get("evidence") or []) if isinstance(item, dict)]
        explicit = [item.get("ok") for item in evidence if "ok" in item]
        return {"name": name, "ok": bool(explicit) and all(value is True for value in explicit)}

    def _task_dir(self, run, task_id: str) -> Path:
        path = run.run_dir / "tasks" / task_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "reports").mkdir(exist_ok=True)
        return path

    def _seed_task_contract(self, run, task: dict[str, Any]) -> Path:
        task_dir = self._task_dir(run, task["id"])
        if (task_dir / "CONTRACT.json").exists():
            return task_dir
        spec_lines = [
            f"# TASK SPEC — {task['id']}",
            "",
            f"## Objective\n{task.get('title') or task['id']}",
            "",
            f"## Profile\n{task['profile'].upper()}",
            "",
            "## Scope",
        ]
        scope = task.get("scope") or []
        spec_lines += [f"- {item}" for item in scope] if scope else ["- Use only the minimum project scope required by this task."]
        spec_lines += ["", "## Dependencies"]
        dependencies = task.get("depends_on") or []
        spec_lines += [f"- {item}" for item in dependencies] if dependencies else ["- None"]
        spec_lines += ["", "## Acceptance Criteria"]
        rubric = []
        for index, criterion in enumerate(task["acceptance"], start=1):
            criterion_id = f"{task['id']}-R-{index:03d}"
            spec_lines.append(f"- {criterion_id}: {criterion}")
            rubric.append(
                {
                    "id": criterion_id,
                    "required": True,
                    "criterion": criterion,
                }
            )
        spec = "\n".join(spec_lines) + "\n"
        (task_dir / "TASK_SPEC.md").write_text(spec, encoding="utf-8")
        (task_dir / "SPEC.md").write_text(spec, encoding="utf-8")
        (task_dir / "RUBRIC.json").write_text(json.dumps({"criteria": rubric}, indent=2) + "\n", encoding="utf-8")
        seal_contract(task_dir)
        EventJournal(run.run_dir).append(
            "TASK_CONTRACT_SEALED",
            task_id=task["id"],
            profile=task["profile"],
            criteria=len(rubric),
        )
        return task_dir

    def _ingest_task(self, task_dir: Path, result: dict[str, Any], role: str) -> None:
        aliases = {
            "TASK_RUBRIC_STATUS.json": "RUBRIC_STATUS.json",
            "TASK_FINDINGS.json": "FINDINGS.json",
            "TASK_FINDINGS.md": "FINDINGS.md",
            "TASK_EVALUATION_REPORT.md": "EVALUATION_REPORT.md",
            "TASK_BUILD_REPORT.md": "BUILD_REPORT.md",
            "TASK_FIX_REPORT.md": "FIX_REPORT.md",
        }
        allowed: dict[str, set[str]] = {
            "RUBRIC_STATUS.json": {"task_evaluator", "content_evaluator", "fact_checker"},
            "FINDINGS.json": {"task_evaluator", "content_evaluator", "fact_checker"},
            "FINDINGS.md": {"task_evaluator", "content_evaluator", "fact_checker"},
            "EVALUATION_REPORT.md": {"task_evaluator", "content_evaluator", "fact_checker"},
            "BUILD_REPORT.md": {"worker", "content_producer", "researcher"},
            "FIX_REPORT.md": {"worker", "fixer", "content_producer", "researcher"},
            "TEST_REPORT.md": {"tester", "content_evaluator", "fact_checker"},
        }
        for raw_name, value in (result.get("artifacts") or {}).items():
            name = aliases.get(str(raw_name), str(raw_name))
            if name in {"SPEC.md", "RUBRIC.json", "RUBRIC_BASELINE.json", "CONTRACT.json", "EVIDENCE.jsonl"}:
                continue
            owners = allowed.get(name)
            if owners is not None and role not in owners:
                continue
            path = task_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            safe = redact_data(value)
            if isinstance(safe, (dict, list)):
                path.write_text(json.dumps(safe, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            else:
                path.write_text(str(safe) + ("" if str(safe).endswith("\n") else "\n"), encoding="utf-8")
        store = EvidenceStore(task_dir)
        for record in result.get("evidence") or []:
            store.append(record)

    @staticmethod
    def _task_findings(task_dir: Path) -> list[dict[str, Any]]:
        path = task_dir / "FINDINGS.json"
        if not path.exists():
            return []
        try:
            return normalize_findings(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return []

    def _task_pending(self, task_dir: Path) -> list[dict[str, Any]]:
        git = GitCheckpoints(self.target)
        severity = {"critical": 0, "major": 1, "minor": 2}
        items = []
        for finding in self._task_findings(task_dir):
            if str(finding.get("status", "open")).lower() != "open":
                continue
            finding_id = str(finding.get("id") or "")
            if finding_id and git.has_finding_commit(finding_id):
                continue
            items.append(finding)
        return sorted(items, key=lambda item: severity.get(str(item.get("severity", "minor")).lower(), 9))

    @staticmethod
    def _task_rubric(task_dir: Path) -> list[dict[str, Any]]:
        statuses = status_map(task_dir)
        return [
            {**item, **statuses.get(str(item["id"]), {}), "id": item["id"], "required": item.get("required", True)}
            for item in baseline_criteria(task_dir)
        ]

    def _task_pipeline(self, run, task: dict[str, Any], context: dict[str, Any], domain: str) -> dict[str, Any]:
        task_id = str(task["id"])
        hinted = str(task["profile"]).lower()
        task_dir = self._seed_task_contract(run, task)
        max_passes = 3
        task_context = {
            **context,
            "task_id": task_id,
            "task_run_dir": str(task_dir),
            "task_spec": str(task_dir / "TASK_SPEC.md"),
            "task_rubric_baseline": str(task_dir / "RUBRIC_BASELINE.json"),
            "global_spec": str(run.run_dir / "SPEC.md"),
            "architecture": str(run.run_dir / "ARCHITECTURE.md"),
        }
        history: list[dict[str, Any]] = []
        last_technical = {"name": "task_technical_tests", "ok": hinted == "lite"}

        for attempt in range(1, max_passes + 1):
            worker_role = role_for(domain, "worker")
            pending = self._task_pending(task_dir)
            mode = "build" if attempt == 1 else "fix"
            worker = self._dispatch(
                run,
                worker_role,
                {
                    **task,
                    "mode": mode,
                    "attempt": attempt,
                    "task_run_dir": str(task_dir),
                    "findings": pending,
                },
                task_context,
                ingest=False,
            )
            self._ingest_task(task_dir, worker, worker_role)

            mandatory: list[dict[str, Any]] = []
            if hinted == "pro":
                tester_role = role_for(domain, "tester")
                test = self._dispatch(
                    run,
                    tester_role,
                    {"mode": "task_test", "task": task, "attempt": attempt, "task_run_dir": str(task_dir)},
                    task_context,
                    ingest=False,
                )
                self._ingest_task(task_dir, test, tester_role)
                last_technical = self._explicit_evidence_gate(test, "task_technical_tests")
                mandatory.append(last_technical)

            evaluator_role = "task_evaluator" if domain in {"code", "operations"} else role_for(domain, "evaluator")
            evaluated = self._dispatch(
                run,
                evaluator_role,
                {
                    "mode": "task_evaluate",
                    "task": task,
                    "attempt": attempt,
                    "task_run_dir": str(task_dir),
                },
                task_context,
                ingest=False,
            )
            self._ingest_task(task_dir, evaluated, evaluator_role)
            gate = FinalGate(task_dir).evaluate(None, self._task_findings(task_dir), mandatory)
            history.append(
                {
                    "attempt": attempt,
                    "done": gate["done"],
                    "gate": gate,
                    "rubric": self._task_rubric(task_dir),
                    "technical": last_technical,
                }
            )
            EventJournal(run.run_dir).append(
                "TASK_EVALUATED",
                task_id=task_id,
                attempt=attempt,
                profile=hinted,
                done=gate["done"],
            )
            if gate["done"]:
                return {"ok": True, "task_id": task_id, "profile": hinted, "history": history, "task_dir": str(task_dir)}

            if attempt < max_passes and not self._task_pending(task_dir):
                EventJournal(run.run_dir).append(
                    "TASK_REVERIFY_WITHOUT_FIX",
                    task_id=task_id,
                    attempt=attempt,
                    reason="no_actionable_findings",
                )

        return {
            "ok": False,
            "task_id": task_id,
            "profile": hinted,
            "history": history,
            "task_dir": str(task_dir),
            "summary": "task did not pass its sealed mini-harness",
        }

    def _validated_graph(self, run, state, context, domain: str) -> TaskGraph | None:
        last_error = "TASKS.json missing"
        for attempt in (1, 2):
            raw = self.store.read_json(run.run_dir, "TASKS.json", None)
            if raw is not None:
                try:
                    return TaskGraph(raw)
                except TaskGraphError as exc:
                    last_error = str(exc)
            state.transition(Phase.ARCHITECTURE, architecture_attempt=attempt, validation_error=last_error)
            self._dispatch(
                run,
                "architect",
                {
                    "mode": "factory_architecture" if attempt == 1 else "repair_task_graph",
                    "domain": domain,
                    "validation_error": last_error,
                    "task_schema": {
                        "required": ["id", "profile", "depends_on", "acceptance"],
                        "profile": ["lite", "pro"],
                        "acceptance": "non-empty measurable pass/fail criteria",
                    },
                },
                context,
            )
        raw = self.store.read_json(run.run_dir, "TASKS.json", None)
        try:
            return TaskGraph(raw)
        except Exception as exc:
            findings = self._findings(run)
            findings.append(
                {
                    "id": "F-TASK-GRAPH",
                    "severity": "major",
                    "status": "open",
                    "rubric_id": None,
                    "detail": f"Architect failed to produce a valid task graph: {exc}",
                }
            )
            self.store.write_json(run.run_dir, "FINDINGS.json", findings)
            EvidenceStore(run.run_dir).append(
                {"id": "E-TASK-GRAPH", "type": "task_graph_validation", "ok": False, "detail": str(exc)}
            )
            return None

    def run(self, request: str, guardian="guarded", domain="code", run_id=None):
        run = self._new(request, guardian, domain, run_id)
        state = self._state(run)
        context = self._context(run, guardian)
        journal = EventJournal(run.run_dir)

        try:
            if not (run.run_dir / "CONTRACT.json").exists():
                state.transition(Phase.PLANNING)
                self._dispatch(
                    run,
                    role_for(domain, "planner"),
                    {"request": request, "mode": "plan", "profile": "factory"},
                    context,
                )
                self._seal(run)

            if not (run.run_dir / "ARCHITECTURE.md").exists() or not (run.run_dir / "TASKS.json").exists():
                state.transition(Phase.ARCHITECTURE)
            graph = self._validated_graph(run, state, context, domain)
            if graph is None:
                gate = self._gate(run, [{"name": "task_graph", "ok": False}])
                state.transition(Phase.PAUSED, status="incomplete", reason="invalid_task_graph")
                return self._write_report(run, gate, {"blocked": "task_graph"})

            completed_outputs = self.store.read_json(run.run_dir, "TASK_OUTPUTS.json", []) or []
            completed_ids = {
                str(item.get("task", {}).get("id"))
                for item in completed_outputs
                if isinstance(item, dict) and item.get("result", {}).get("ok") is True
            }
            task_outputs = list(completed_outputs)

            for task in graph.order():
                if task["id"] in completed_ids:
                    journal.append("TASK_RESUME_SKIP", task_id=task["id"], reason="already_verified")
                    continue
                state.transition(Phase.BUILDING, current_task=task["id"])
                result = self._task_pipeline(run, task, context, domain)
                task_outputs.append({"task": task, "result": result})
                self.store.write_json(run.run_dir, "TASK_OUTPUTS.json", task_outputs)
                if not result["ok"]:
                    findings = self._findings(run)
                    findings.append(
                        {
                            "id": f"TASK-{task['id']}",
                            "severity": "major",
                            "status": "open",
                            "rubric_id": None,
                            "detail": "Task failed its independent sealed task harness",
                        }
                    )
                    self.store.write_json(run.run_dir, "FINDINGS.json", findings)
                    gate = self._gate(run, [{"name": "task_graph", "ok": False}])
                    state.transition(Phase.PAUSED, status="incomplete", blocked_task=task["id"])
                    return self._write_report(
                        run,
                        gate,
                        {"tasks_completed": len(completed_ids), "blocked_task": task["id"], "task_outputs": task_outputs},
                    )
                completed_ids.add(task["id"])

            state.transition(Phase.INTEGRATING)
            self._dispatch(
                run,
                "integrator",
                {"mode": "integrate", "tasks": {"tasks": graph.tasks}, "outputs": task_outputs, "domain": domain},
                context,
            )
            journal.append("INTEGRATION_COMPLETED", tasks=len(graph.tasks))

            system_role = "system_tester" if domain in {"code", "operations"} else role_for(domain, "tester")
            state.transition(Phase.TESTING)
            system_result = self._dispatch(
                run,
                system_role,
                {"mode": "system_test", "domain": domain, "profile": "factory"},
                context,
            )
            system_gate = self._explicit_evidence_gate(system_result, "system_test")

            state.transition(Phase.EVALUATING)
            self._dispatch(
                run,
                role_for(domain, "evaluator"),
                {"mode": "system_evaluate", "domain": domain, "profile": "factory"},
                context,
            )

            mandatory = [
                {"name": "task_graph", "ok": len(completed_ids) == len(graph.tasks)},
                system_gate,
            ]

            state.transition(Phase.REVIEWING)
            if domain in {"code", "operations"}:
                security = self._dispatch(
                    run,
                    "security_reviewer",
                    {"mode": "security_review", "domain": domain, "profile": "factory"},
                    context,
                )
                security_evidence = [
                    item for item in (security.get("evidence") or [])
                    if isinstance(item, dict) and str(item.get("type") or item.get("kind")) == "security"
                ]
                explicit = [item.get("ok") for item in security_evidence if "ok" in item]
                mandatory.append({"name": "security", "ok": bool(explicit) and all(value is True for value in explicit)})

            self._dispatch(
                run,
                "final_reviewer",
                {"mode": "final_review", "domain": domain, "profile": "factory"},
                context,
            )

            gate = self._gate(run, mandatory)
            state.transition(
                Phase.DONE if gate["done"] else Phase.PAUSED,
                status="done" if gate["done"] else "incomplete",
            )
            return self._write_report(
                run,
                gate,
                {"tasks": len(graph.tasks), "task_outputs": task_outputs},
            )
        except AgentDispatchError as exc:
            return self._abort(run, state, exc, state.load().get("phase", "factory"))
        except Exception as exc:
            return self._abort(run, state, exc, state.load().get("phase", "factory"))
