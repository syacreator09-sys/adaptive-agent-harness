from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from ..artifacts import ArtifactStore
from ..contracts import baseline_criteria, seal_contract, status_map
from ..evidence import EvidenceStore, redact_data
from ..events import EventJournal
from ..state import RunStateStore
from ..models import Phase
from ..final_gate import FinalGate, normalize_findings
from ..project_adapter import ProjectAdapter
from ..gitops import GitCheckpoints


_RUNTIME_OWNED = {
    "STATE.json", "REQUEST.json", "EVENTS.jsonl", "AGENTS.jsonl", "EVIDENCE.jsonl",
    "CONTRACT.json", "RUBRIC_BASELINE.json", "FINAL_REPORT.json", "FINAL_REPORT.md",
}
_ROLE_WRITERS: dict[str, set[str]] = {
    "SPEC.md": {"planner", "content_strategist"},
    "RUBRIC.json": {"planner", "content_strategist"},
    "PLANNING_REPORT.md": {"planner", "content_strategist"},
    "ARCHITECTURE.md": {"architect"},
    "TASKS.json": {"architect"},
    "ARCHITECTURE_REPORT.md": {"architect"},
    "RUBRIC_STATUS.json": {"evaluator", "content_evaluator", "fact_checker"},
    "FINDINGS.json": {"evaluator", "content_evaluator", "fact_checker"},
    "FINDINGS.md": {"evaluator", "content_evaluator", "fact_checker"},
    "EVALUATION_REPORT.md": {"evaluator", "content_evaluator", "fact_checker"},
    "BUILD_REPORT.md": {"builder", "content_producer", "researcher"},
    "FIX_REPORT.md": {"builder", "fixer", "content_producer", "researcher"},
    "TEST_REPORT.md": {"tester"},
    "INTEGRATION_REPORT.md": {"integrator"},
    "SYSTEM_TEST_REPORT.md": {"system_tester", "tester", "content_evaluator", "fact_checker"},
    "SECURITY_REPORT.md": {"security_reviewer"},
    "REVIEW_REPORT.md": {"final_reviewer"},
}


class AgentDispatchError(RuntimeError):
    pass


class BaseRunner:
    profile = "base"

    def __init__(self, target: Path | str, executor):
        self.target = Path(target).resolve()
        self.executor = executor
        self.store = ArtifactStore(self.target)

    def _new(self, request, guardian, domain="code", run_id=None):
        if run_id:
            return self.store.get_run(run_id)
        run = self.store.create_run(request, self.profile, guardian, domain)
        snapshot = GitCheckpoints(self.target).snapshot()
        state = self._state(run).load()
        state["git_base"] = snapshot.get("head")
        state["git_base_dirty"] = snapshot.get("dirty", False)
        state["git_worktree"] = snapshot.get("is_linked_worktree", False)
        self._state(run).save(state)
        request_doc = self.store.read_json(run.run_dir, "REQUEST.json", {})
        request_doc["git_base"] = snapshot.get("head")
        self.store.write_json(run.run_dir, "REQUEST.json", request_doc)
        EventJournal(run.run_dir).append(
            "RUN_CREATED",
            run_id=run.run_id,
            profile=self.profile,
            guardian=guardian,
            domain=domain,
            git_base=snapshot.get("head"),
            dirty_baseline=snapshot.get("dirty", False),
        )
        return run

    def _context(self, run, guardian):
        request_doc = self.store.read_json(run.run_dir, "REQUEST.json", {}) or {}
        return {
            "run_id": run.run_id,
            "run_dir": str(run.run_dir),
            "request": request_doc.get("request", ""),
            "guardian": guardian,
            "profile": self.profile,
            "project": ProjectAdapter(self.target).inspect(),
            "artifact_protocol": (
                "AAH coordination lives under run_dir. Read the sealed contract from SPEC.md + "
                "RUBRIC_BASELINE.json after planning. Never use another agent's conclusion as proof."
            ),
        }

    def _record_policy_violation(self, run, role: str, name: str) -> None:
        finding_id = f"F-POLICY-{role}-{name}".replace("/", "-").replace(".", "-")
        findings = self._findings(run)
        if not any(str(item.get("id")) == finding_id and str(item.get("status", "open")).lower() == "open" for item in findings):
            findings.append(
                {
                    "id": finding_id,
                    "severity": "major",
                    "status": "open",
                    "rubric_id": None,
                    "detail": f"Role {role} attempted to overwrite protected artifact {name}",
                }
            )
            self.store.write_json(run.run_dir, "FINDINGS.json", findings)
        EvidenceStore(run.run_dir).append(
            {"type": "artifact_policy_violation", "ok": False, "role": role, "artifact": name}
        )
        EventJournal(run.run_dir).append("POLICY_VIOLATION", role=role, artifact=name)

    def _ingest(self, run, result):
        role = str(result.get("_aah_role") or "unknown")
        for name, value in (result.get("artifacts") or {}).items():
            name = str(name)
            if name in _RUNTIME_OWNED:
                self._record_policy_violation(run, role, name)
                continue
            allowed = _ROLE_WRITERS.get(name)
            if allowed is not None and role not in allowed:
                self._record_policy_violation(run, role, name)
                continue
            safe = redact_data(value)
            if isinstance(safe, (dict, list)):
                self.store.write_json(run.run_dir, name, safe)
            else:
                self.store.write_text(run.run_dir, name, str(safe))

        evidence = EvidenceStore(run.run_dir)
        for record in result.get("evidence") or []:
            evidence.append(record)

    def _record_agent(self, run, role: str, task: dict[str, Any], result: dict[str, Any], attempt: int) -> None:
        assignment = result.get("_aah_assignment") or {}
        record = {
            "role": role,
            "session": result.get("_aah_session") or result.get("session"),
            "provider": assignment.get("provider") or result.get("provider"),
            "model": assignment.get("model") or result.get("provider_raw_model"),
            "capability": assignment.get("capability"),
            "effort": assignment.get("effort"),
            "mode": task.get("mode"),
            "pass": task.get("pass") or task.get("attempt"),
            "task_id": task.get("id") or (task.get("task") or {}).get("id") if isinstance(task.get("task"), dict) else task.get("id"),
            "dispatch_attempt": attempt,
        }
        self.store.append_jsonl(run.run_dir, "AGENTS.jsonl", redact_data(record))

        report_index = len(EventJournal(run.run_dir).all()) + 1
        safe_role = role.replace("/", "-")
        report_name = f"reports/{report_index:04d}-{safe_role}.md"
        summary = str(result.get("summary") or "No summary returned.")
        lines = [
            f"# Agent Report — {role}",
            "",
            f"Session: `{record['session']}`",
            f"Provider: `{record['provider']}`",
            f"Model: `{record['model']}`",
            f"Capability: `{record['capability']}`",
            f"Mode: `{record['mode']}`",
            "",
            "## Summary",
            "",
            summary,
        ]
        self.store.write_text(run.run_dir, report_name, str(redact_data("\n".join(lines))))

    def _dispatch(self, run, role: str, task: dict[str, Any], context: dict[str, Any], ingest: bool = True):
        journal = EventJournal(run.run_dir)
        last_error: Exception | None = None
        for attempt in (1, 2):
            journal.append("AGENT_STARTED", role=role, mode=task.get("mode"), attempt=attempt, task_id=task.get("id"))
            try:
                result = self.executor.execute(role, task, context)
                result.setdefault("_aah_role", role)
                if ingest:
                    self._ingest(run, result)
                self._record_agent(run, role, task, result, attempt)
                journal.append(
                    "AGENT_FINISHED",
                    role=role,
                    session=result.get("_aah_session") or result.get("session"),
                    attempt=attempt,
                )
                return result
            except Exception as exc:
                last_error = exc
                journal.append(
                    "AGENT_ERROR",
                    role=role,
                    attempt=attempt,
                    error=type(exc).__name__,
                    detail=str(exc)[:1000],
                )
                if attempt == 1:
                    journal.append("AGENT_RETRY", role=role, reason="first_failure")
        raise AgentDispatchError(f"{role} failed twice: {last_error}") from last_error

    def _seal(self, run) -> dict[str, Any]:
        contract = seal_contract(run.run_dir)
        checkpoint = GitCheckpoints(self.target).planning_checkpoint(run.run_id)
        self.store.write_json(run.run_dir, "checkpoints/planning.json", checkpoint)
        state = self._state(run).load()
        state["contract"] = contract
        state["planning_checkpoint"] = checkpoint
        self._state(run).save(state)
        EventJournal(run.run_dir).append(
            "CONTRACT_SEALED",
            spec_sha256=contract.get("spec_sha256"),
            rubric_sha256=contract.get("rubric_sha256"),
            required_criteria=contract.get("required_criteria"),
            git_checkpoint=checkpoint.get("head"),
        )
        return contract

    def _rubric(self, run) -> list[dict[str, Any]]:
        baseline = baseline_criteria(run.run_dir)
        statuses = status_map(run.run_dir)
        rows: list[dict[str, Any]] = []
        for item in baseline:
            status = statuses.get(str(item["id"]), {})
            rows.append({**item, **status, "id": item["id"], "required": item.get("required", True)})
        return rows

    def _findings(self, run) -> list[dict[str, Any]]:
        return normalize_findings(self.store.read_json(run.run_dir, "FINDINGS.json", []))

    def _pending_findings(self, run) -> list[dict[str, Any]]:
        git = GitCheckpoints(self.target)
        pending: list[dict[str, Any]] = []
        for finding in self._findings(run):
            if str(finding.get("status", "open")).lower() != "open":
                continue
            finding_id = str(finding.get("id") or "")
            if finding_id and git.has_finding_commit(finding_id):
                EventJournal(run.run_dir).append("FINDING_ALREADY_COMMITTED", finding_id=finding_id)
                continue
            pending.append(finding)
        severity = {"critical": 0, "major": 1, "minor": 2}
        return sorted(pending, key=lambda item: severity.get(str(item.get("severity", "minor")).lower(), 9))

    def _gate(self, run, mandatory=None):
        return FinalGate(run.run_dir).evaluate(None, self._findings(run), mandatory)

    def _state(self, run):
        return RunStateStore(run.run_dir)

    def _abort(self, run, state, error: Exception, phase: str) -> dict[str, Any]:
        finding_id = f"F-RUNTIME-{phase.upper()}"
        findings = self._findings(run)
        findings.append(
            {
                "id": finding_id,
                "severity": "critical",
                "status": "open",
                "rubric_id": None,
                "detail": f"Runtime stopped after bounded retry: {type(error).__name__}: {str(error)[:800]}",
            }
        )
        self.store.write_json(run.run_dir, "FINDINGS.json", findings)
        EvidenceStore(run.run_dir).append(
            {"id": f"E-{finding_id}", "type": "runtime_failure", "ok": False, "detail": str(error)[:800]}
        )
        EventJournal(run.run_dir).append("RUN_ABORTED", phase=phase, error=type(error).__name__, detail=str(error)[:1000])
        state.transition(Phase.FAILED, status="failed", failure_phase=phase)
        gate = self._gate(run, [{"name": "runtime", "ok": False}])
        return self._write_report(run, gate, {"runtime_error": str(error), "failure_phase": phase})

    def _write_report(self, run, gate, extra=None):
        state = self._state(run).load()
        state["git_current"] = GitCheckpoints(self.target).snapshot().get("head")
        self._state(run).save(state)
        agents: list[dict[str, Any]] = []
        agents_path = run.run_dir / "AGENTS.jsonl"
        if agents_path.exists():
            for line in agents_path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        agents.append(value)
                except Exception:
                    pass
        findings = self._findings(run)
        counts = {severity: 0 for severity in ["critical", "major", "minor"]}
        for finding in findings:
            if str(finding.get("status", "open")).lower() == "open":
                severity = str(finding.get("severity", "minor")).lower()
                counts[severity] = counts.get(severity, 0) + 1
        report = {
            "run_id": run.run_id,
            "profile": self.profile,
            "done": gate["done"],
            "gate": gate,
            "state": state,
            "agents": agents,
            "open_findings": counts,
            "extra": redact_data(extra or {}),
        }
        self.store.write_json(run.run_dir, "FINAL_REPORT.json", report)
        lines = [
            f"# AAH Final Report — {run.run_id}",
            "",
            f"Profile: **{self.profile.upper()}**",
            f"Done: **{gate['done']}**",
            f"Rubric: **{gate['passed']}/{gate['required']}**",
            f"Contract sealed: **{gate.get('contract_sealed', False)}**",
            f"Open findings: critical={counts.get('critical', 0)}, major={counts.get('major', 0)}, minor={counts.get('minor', 0)}",
            "",
            "## Agent invocations",
        ]
        for agent in agents:
            lines.append(
                f"- {agent.get('role')} — session `{agent.get('session')}` — "
                f"{agent.get('provider')}/{agent.get('model')} — mode `{agent.get('mode')}`"
            )
        if gate["failures"]:
            lines += ["", "## Blocking items"] + [f"- {item}" for item in gate["failures"]]
        self.store.write_text(run.run_dir, "FINAL_REPORT.md", "\n".join(lines))
        EventJournal(run.run_dir).append("FINAL_REPORT_WRITTEN", done=gate["done"], failures=len(gate["failures"]))
        return report
