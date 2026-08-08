from __future__ import annotations
from pathlib import Path
from typing import Any
from .router import AdaptiveRouter
from .profiles import LiteRunner, ProRunner, FactoryRunner
from .artifacts import ArtifactStore
from .final_gate import normalize_findings


class AutoOrchestrator:
    ORDER = ["lite", "pro", "factory"]
    RUNNERS = {"lite": LiteRunner, "pro": ProRunner, "factory": FactoryRunner}

    def __init__(
        self,
        target: Path | str,
        executor_factory,
        router: AdaptiveRouter,
        limits: dict[str, Any] | None = None,
    ):
        self.target = Path(target).resolve()
        self.executor_factory = executor_factory
        self.router = router
        self.store = ArtifactStore(self.target)
        self.limits = limits or {}

    def _run_profile(self, profile: str, request: str, guardian: str, domain: str, run_id: str | None = None):
        executor = self.executor_factory(profile, domain)
        runner = self.RUNNERS[profile](self.target, executor)
        kwargs: dict[str, Any] = {"guardian": guardian, "domain": domain, "run_id": run_id}
        if profile == "lite":
            kwargs["max_passes"] = int(self.limits.get("max_lite_passes", 3))
        elif profile == "pro":
            kwargs["max_passes"] = int(self.limits.get("max_pro_passes", 5))
        return runner.run(request, **kwargs)

    def _seed_child(
        self,
        parent_run_id: str,
        next_profile: str,
        request: str,
        guardian: str,
        domain: str,
        failures: list[str] | None = None,
    ):
        parent = self.store.get_run(parent_run_id)
        child = self.store.create_run(request, next_profile, guardian, domain)

        spec = parent.run_dir / "SPEC.md"
        if spec.exists():
            self.store.write_text(child.run_dir, "SPEC.md", spec.read_text(encoding="utf-8"))

        baseline = self.store.read_json(parent.run_dir, "RUBRIC_BASELINE.json", None)
        if baseline is None:
            baseline = self.store.read_json(parent.run_dir, "RUBRIC.json", None)
        if baseline is not None:
            self.store.write_json(child.run_dir, "RUBRIC.json", baseline)

        findings = normalize_findings(self.store.read_json(parent.run_dir, "FINDINGS.json", []))
        if findings:
            self.store.write_json(child.run_dir, "FINDINGS.json", findings)

        context = {
            "parent_run_id": parent_run_id,
            "from_profile": self.store.read_json(parent.run_dir, "REQUEST.json", {}).get("profile"),
            "to_profile": next_profile,
            "failures": list(failures or []),
            "open_findings": [
                item for item in findings
                if str(item.get("status", "open")).lower() == "open"
            ],
            "evidence_inherited_as_proof": False,
            "rubric_status_reset": True,
        }
        self.store.write_json(child.run_dir, "PARENT_RUN.json", {"parent_run_id": parent_run_id})
        self.store.write_json(child.run_dir, "ESCALATION_CONTEXT.json", context)
        return child

    def run(self, request: str, domain="code", profile="auto", guardian="auto") -> dict[str, Any]:
        route = self.router.route(request)
        current = route["profile"] if profile == "auto" else profile
        guard = route["guardian"] if guardian == "auto" else guardian
        chain: list[dict[str, Any]] = []
        run_id: str | None = None

        while True:
            result = self._run_profile(current, request, guard, domain, run_id=run_id)
            current_run_id = result["run_id"]
            chain.append({"profile": current, "run_id": current_run_id, "done": result["done"]})

            if result["done"] or profile != "auto":
                result["chain"] = chain
                result["route"] = route
                return result

            next_profile = (result.get("extra") or {}).get("escalation")
            if next_profile not in self.ORDER or self.ORDER.index(next_profile) <= self.ORDER.index(current):
                result["chain"] = chain
                result["route"] = route
                return result

            child = self._seed_child(
                current_run_id,
                next_profile,
                request,
                guard,
                domain,
                failures=(result.get("gate") or {}).get("failures", []),
            )
            run_id = child.run_id
            current = next_profile
