from __future__ import annotations
from ..models import Phase
from ..domains import role_for, gate_types
from ..progress import ProgressDetector
from ..events import EventJournal
from .common import BaseRunner, AgentDispatchError


class ProRunner(BaseRunner):
    profile = "pro"

    @staticmethod
    def _technical_gate(result, domain: str) -> dict:
        labels = gate_types(domain, "pro_test")
        evidence = [
            item for item in (result.get("evidence") or [])
            if isinstance(item, dict)
            and str(item.get("type") or item.get("kind") or "") in labels
        ]
        explicit = [item.get("ok") for item in evidence if "ok" in item]
        return {"name": "technical_tests", "ok": bool(explicit) and all(value is True for value in explicit)}

    def run(self, request: str, guardian="guarded", domain="code", run_id=None, max_passes=5):
        max_passes = max(1, min(int(max_passes), 5))
        run = self._new(request, guardian, domain, run_id)
        state = self._state(run)
        context = self._context(run, guardian)
        journal = EventJournal(run.run_dir)
        history: list[dict] = []

        try:
            self._ensure_contract(run, state, context, request, domain, "pro")

            if not (run.run_dir / "ARCHITECTURE.md").exists():
                state.transition(Phase.ARCHITECTURE)
                self._dispatch(run, "architect", {"mode": "architecture", "profile": "pro"}, context)
                journal.append("ARCHITECTURE_COMPLETED")

            build_checkpoint = run.run_dir / "checkpoints" / "build.json"
            if not build_checkpoint.exists():
                state.transition(Phase.BUILDING)
                result = self._dispatch(
                    run,
                    role_for(domain, "builder"),
                    {"mode": "build", "profile": "pro", "request": request},
                    context,
                )
                self.store.write_json(
                    run.run_dir,
                    "checkpoints/build.json",
                    {"completed": True, "session": result.get("_aah_session") or result.get("session")},
                )
                journal.append("BUILD_COMPLETED", session=result.get("_aah_session") or result.get("session"))

            detector = ProgressDetector()
            start_pass = max(1, int(state.load().get("pass", 0)) + 1)
            rediagnosed = (run.run_dir / "checkpoints" / "architecture-rediagnosis.json").exists()
            last_test_gate = {"name": "technical_tests", "ok": False}

            for pass_no in range(start_pass, max_passes + 1):
                state.transition(Phase.TESTING, **{"pass": pass_no})
                test_result = self._dispatch(
                    run,
                    role_for(domain, "tester"),
                    {"mode": "test", "pass": pass_no, "profile": "pro"},
                    context,
                )
                last_test_gate = self._technical_gate(test_result, domain)
                journal.append("TECHNICAL_TEST_COMPLETED", pass_no=pass_no, ok=last_test_gate["ok"])

                state.transition(Phase.EVALUATING, **{"pass": pass_no})
                self._dispatch(
                    run,
                    role_for(domain, "evaluator"),
                    {"mode": "evaluate", "pass": pass_no, "profile": "pro"},
                    context,
                )
                rubric = self._rubric(run)
                findings = self._findings(run)
                gate = self._gate(run, [last_test_gate])
                passed, total = detector.score(rubric)
                history.append({
                    "passed": passed,
                    "total": total,
                    "open_findings": sum(
                        1 for item in findings if str(item.get("status", "open")).lower() == "open"
                    ),
                })
                journal.append(
                    "EVALUATION_COMPLETED",
                    pass_no=pass_no,
                    done=gate["done"],
                    passed=passed,
                    required=total,
                )
                if gate["done"]:
                    state.transition(Phase.DONE, status="done")
                    return self._write_report(run, gate, {"passes": pass_no, "progress": history})

                progress = detector.assess(history)
                if progress.get("stalled") and pass_no >= 2 and not rediagnosed:
                    state.transition(Phase.ARCHITECTURE, reason="no_progress_rediagnosis")
                    self._dispatch(
                        run,
                        "architect",
                        {
                            "mode": "rediagnose",
                            "profile": "pro",
                            "history": history,
                            "open_findings": self._pending_findings(run),
                        },
                        context,
                    )
                    self.store.write_json(
                        run.run_dir,
                        "checkpoints/architecture-rediagnosis.json",
                        {"completed": True, "after_pass": pass_no},
                    )
                    rediagnosed = True
                    journal.append("ARCHITECTURE_REDIAGNOSIS", pass_no=pass_no)

                if pass_no < max_passes:
                    pending = self._pending_findings(run)
                    if pending:
                        state.transition(Phase.FIXING)
                        self._dispatch(
                            run,
                            role_for(domain, "fixer"),
                            {
                                "mode": "fix",
                                "pass": pass_no,
                                "profile": "pro",
                                "findings": pending,
                            },
                            context,
                        )
                        journal.append(
                            "FIX_COMPLETED",
                            pass_no=pass_no,
                            finding_ids=[item.get("id") for item in pending],
                        )
                    else:
                        journal.append(
                            "REVERIFY_WITHOUT_FIX",
                            pass_no=pass_no,
                            reason="no_actionable_findings",
                        )

                if progress.get("stalled") and rediagnosed and pass_no >= 3:
                    journal.append("PRO_STALLED", pass_no=pass_no, history=history)
                    break

            gate = self._gate(run, [last_test_gate])
            state.transition(Phase.PAUSED, status="incomplete", escalation="factory")
            journal.append(
                "ESCALATION_RECOMMENDED",
                from_profile="pro",
                to_profile="factory",
                failures=gate["failures"],
            )
            return self._write_report(
                run,
                gate,
                {
                    "passes": int(state.load().get("pass", max_passes)),
                    "progress": history,
                    "escalation": "factory",
                },
            )
        except AgentDispatchError as exc:
            return self._abort(run, state, exc, state.load().get("phase", "pro"))
        except Exception as exc:
            return self._abort(run, state, exc, state.load().get("phase", "pro"))
