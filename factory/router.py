from __future__ import annotations
from typing import Any
from .models import RouteDecision
from .agents import AgentRegistry
from .model_router import ModelRouter


_PRODUCERS = {
    "builder", "fixer", "worker", "integrator", "content_producer", "researcher",
}
_REVIEWERS = {
    "tester", "evaluator", "task_evaluator", "system_tester", "security_reviewer",
    "final_reviewer", "content_evaluator", "fact_checker",
}


class AdaptiveRouter:
    def __init__(self, providers: dict[str, dict[str, Any]], registry: AgentRegistry | None = None):
        self.providers = providers
        self.registry = registry or AgentRegistry()

    def score(self, request: str) -> tuple[int, int, list[str]]:
        text = request.lower()
        complexity, risk, reasons = 10, 5, []
        complex_terms = {
            "architecture": 20, "multi-service": 30, "platform": 30, "factory": 30,
            "migration": 20, "refactor": 20, "dashboard": 10, "database": 15,
            "api": 10, "full": 15, "complete": 15,
        }
        risk_terms = {
            "production": 45, "prod": 35, "payment": 35, "billing": 30,
            "auth": 30, "authentication": 30, "delete": 35, "migration": 20,
            "database": 15, "secret": 25, "credential": 25, "vps": 20, "dns": 25,
        }
        for term, points in complex_terms.items():
            if term in text:
                complexity += points
                reasons.append(f"complex:{term}")
        for term, points in risk_terms.items():
            if term in text:
                risk += points
                reasons.append(f"risk:{term}")
        if len(text) > 500:
            complexity += 20
        elif len(text) > 200:
            complexity += 10
        return min(100, complexity), min(100, risk), reasons

    def route(self, request: str, complexity_hint: int | None = None, risk_hint: int | None = None) -> dict[str, Any]:
        complexity, risk, reasons = self.score(request)
        if complexity_hint is not None:
            complexity = max(0, min(100, int(complexity_hint)))
        if risk_hint is not None:
            risk = max(0, min(100, int(risk_hint)))
        profile = "lite" if complexity <= 25 else "pro" if complexity <= 70 else "factory"
        guardian = "open" if risk < 30 else "guarded" if risk < 70 else "locked"
        return RouteDecision(profile, guardian, complexity, risk, reasons).to_dict()

    def available(self) -> list[str]:
        return [
            name for name, info in self.providers.items()
            if info.get("available") and info.get("authenticated") is not False
        ]

    def _capability(self, role: str) -> str:
        try:
            return str(self.registry.get(role).get("capability") or "strong_coding")
        except Exception:
            return "strong_coding"

    @staticmethod
    def _default_provider(role: str, available: list[str], producer_provider: str | None) -> str:
        if role in _PRODUCERS:
            return "codex" if "codex" in available else available[0]
        if role in _REVIEWERS and producer_provider and len(available) > 1:
            return next(name for name in available if name != producer_provider)
        return "claude" if "claude" in available else available[0]

    def assign_roles(
        self,
        roles: list[str],
        policy: str = "balanced",
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        overrides = overrides or {}
        available = self.available()
        if not available:
            return {
                role: {"provider": "none", "model": None, "model_candidates": [], "capability": self._capability(role)}
                for role in roles
            }

        result: dict[str, dict[str, Any]] = {}
        producer_provider: str | None = None

        for role in roles:
            capability = self._capability(role)
            provider = self._default_provider(role, available, producer_provider)
            patch = overrides.get(role) or {}
            if patch and not isinstance(patch, dict):
                raise ValueError(f"Model override for {role} must be an object")
            if patch.get("provider"):
                provider = str(patch["provider"])
            if provider not in available:
                raise ValueError(f"Configured provider {provider!r} for {role} is not available/authenticated")

            plan = ModelRouter.resolve(provider, capability, policy).to_dict()
            assignment = dict(plan)
            assignment["provider"] = provider
            if "model" in patch:
                assignment["model"] = patch["model"]
                assignment["model_candidates"] = [patch["model"]] if patch["model"] else []
            if "effort" in patch:
                assignment["effort"] = patch["effort"]
            for key, value in patch.items():
                if key not in {"provider", "model", "effort"}:
                    assignment[key] = value
            result[role] = assignment

            if role in _PRODUCERS:
                producer_provider = provider

        # If both providers exist, a global evaluator should not share the producer provider
        # unless the operator explicitly chose that provider.
        if (
            "evaluator" in result
            and producer_provider
            and len(available) > 1
            and "provider" not in (overrides.get("evaluator") or {})
            and result["evaluator"]["provider"] == producer_provider
        ):
            provider = next(name for name in available if name != producer_provider)
            plan = ModelRouter.resolve(provider, self._capability("evaluator"), policy).to_dict()
            plan["provider"] = provider
            result["evaluator"] = plan

        return result
