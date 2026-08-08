from __future__ import annotations
from ..models import Phase
from ..domains import role_for
from ..events import EventJournal
from .common import BaseRunner, AgentDispatchError


class LiteRunner(BaseRunner):
    """Minimal reliable writer/verifier loop.

    LITE intentionally stays small: Planner -> Builder -> fresh Evaluator.
    Fixes reuse the Builder identity in FIX mode, while every evaluation is a
    new provider process/session. Infrastructure around the three brains is
    stronger, but agent count remains minimal.
    """

    profile = "lite"

    def run(self, request: str, guardian="open", domain="code", run_id=None, max_passes=3):
        max_passes = max(1, min(int(max_passes), 3))
        run = self._new(request, guardian, domain, run_id)
        state = self._state(run)
        context = self._context(run, guardian)
        journal = EventJournal(run.run_dir)

        try:
            self._ensure_contract(run, state, context, request, domain, "lite")

            build_checkpoint = run.run_dir / "checkpoints" / "build.json"
            if not build_checkpoint.exists():
                state.transition(Phase.BUILDING)
                result = self._dispatch(
                    run,
                    role_for(domain, "builder"),
                    {"mode": "build", "request": request, "profile": "lite"},
                    context,
                )
                self.store.write_json(
                    run.run_dir,
                    "checkpoints/build.json",
                    {"completed": True, "session": result.get("_aah_session") or result.get("session")},
                )
                journal.append("BUILD_COMPLETED", session=result.get("_aah_session") or result.get("session"))

            state_data = state.load()
            start_pass = max(1, int(state_data.get("pass", 0)) + 1)
            previous_open: tuple[str, ...] | None = None

            for pass_no in range(start_pass, max_passes + 1):
                state.transition(Phase.EVALUATING, **{"pass": pass_no})
                self._dispatch(
                    run,
                    role_for(domain, "evaluator"),
                    {"mode": "evaluate", "pass": pass_no, "profile": "lite"},
                    context,
                )
                gate = self._gate(run)
                journal.append(
                    "EVALUATION_COMPLETED",
                    pass_no=pass_no,
                    done=gate["done"],
                    failures=gate["failures"],
                )
                if gate["done"]:
                    state.transition(Phase.DONE, status="done")
                    return self._write_report(run, gate, {"passes": pass_no})

                pending = self._pending_findings(run)
                blocking_ids = tuple(sorted(
                    str(item.get("id"))
                    for item in pending
                    if str(item.get("severity", "")).lower() in {"critical", "major"}
                ))
                if blocking_ids and previous_open == blocking_ids:
                    journal.append("LITE_STALLED", pass_no=pass_no, repeated_findings=list(blocking_ids))
                    break
                if blocking_ids:
                    previous_open = blocking_ids

                if pass_no < max_passes and pending:
                    state.transition(Phase.FIXING)
                    self._dispatch(
                        run,
                        role_for(domain, "builder"),
                        {
                            "mode": "fix",
                            "pass": pass_no,
                            "profile": "lite",
                            "findings": pending,
                        },
                        context,
                    )
                    journal.append(
                        "FIX_COMPLETED",
                        pass_no=pass_no,
                        finding_ids=[item.get("id") for item in pending],
                    )
                elif pass_no < max_passes:
                    journal.append(
                        "REVERIFY_WITHOUT_FIX",
                        pass_no=pass_no,
                        reason="no_actionable_findings",
                    )

            gate = self._gate(run)
            state.transition(Phase.PAUSED, status="incomplete", escalation="pro")
            journal.append(
                "ESCALATION_RECOMMENDED",
                from_profile="lite",
                to_profile="pro",
                failures=gate["failures"],
            )
            return self._write_report(
                run,
                gate,
                {
                    "passes": min(max_passes, int(state.load().get("pass", max_passes))),
                    "escalation": "pro",
                },
            )
        except AgentDispatchError as exc:
            return self._abort(run, state, exc, state.load().get("phase", "lite"))
        except Exception as exc:
            return self._abort(run, state, exc, state.load().get("phase", "lite"))
