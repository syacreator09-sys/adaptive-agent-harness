from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelPlan:
    provider: str
    capability: str
    policy: str
    recommended: str | None
    candidates: tuple[str, ...]
    effort: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "capability": self.capability,
            "policy": self.policy,
            "model": self.recommended,
            "model_candidates": list(self.candidates),
            "effort": self.effort,
        }


# These are preference orders, not assumptions that every account exposes every
# model. Provider adapters may fall back only when the CLI reports a model/access
# selection error; arbitrary runtime failures are never replayed on another model.
_CLAUDE: dict[str, dict[str, tuple[str, ...]]] = {
    "quality": {
        "deep_reasoning": ("claude-opus-5", "claude-opus-4-8", "claude-sonnet-5"),
        "strong_coding": ("claude-opus-5", "claude-opus-4-8", "claude-sonnet-5"),
        "architecture_high": ("claude-opus-5", "claude-opus-4-8", "claude-sonnet-5"),
        "independent_review": ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-8"),
        "fast_verification": ("claude-sonnet-5", "claude-opus-4-8"),
        "security_review": ("claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"),
        "integration_high": ("claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"),
    },
    "balanced": {
        # Keep LITE's producer side strong, while verification uses a different
        # model family when possible, mirroring the writer/verifier separation.
        "deep_reasoning": ("claude-opus-5", "claude-opus-4-8", "claude-sonnet-5"),
        "strong_coding": ("claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"),
        "architecture_high": ("claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"),
        "independent_review": ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-8"),
        "fast_verification": ("claude-sonnet-5", "claude-opus-4-8"),
        "security_review": ("claude-opus-5", "claude-sonnet-5"),
        "integration_high": ("claude-opus-5", "claude-sonnet-5"),
    },
    "economy": {
        "deep_reasoning": ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-8"),
        "strong_coding": ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-8"),
        "architecture_high": ("claude-sonnet-5", "claude-opus-5"),
        "independent_review": ("claude-sonnet-5", "claude-opus-4-8"),
        "fast_verification": ("claude-sonnet-5",),
        "security_review": ("claude-sonnet-5", "claude-opus-5"),
        "integration_high": ("claude-sonnet-5", "claude-opus-5"),
    },
}

_OPENAI: dict[str, dict[str, tuple[str, ...]]] = {
    "quality": {
        "deep_reasoning": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
        "strong_coding": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
        "architecture_high": ("gpt-5.6-sol", "gpt-5.6-terra"),
        # Prefer a distinct verifier tier when the producer also used Sol.
        "independent_review": ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"),
        "fast_verification": ("gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-sol"),
        "security_review": ("gpt-5.6-sol", "gpt-5.6-terra"),
        "integration_high": ("gpt-5.6-sol", "gpt-5.6-terra"),
    },
    "balanced": {
        "deep_reasoning": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
        "strong_coding": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
        "architecture_high": ("gpt-5.6-sol", "gpt-5.6-terra"),
        "independent_review": ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"),
        "fast_verification": ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
        "security_review": ("gpt-5.6-sol", "gpt-5.6-terra"),
        "integration_high": ("gpt-5.6-sol", "gpt-5.6-terra"),
    },
    "economy": {
        "deep_reasoning": ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"),
        "strong_coding": ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"),
        "architecture_high": ("gpt-5.6-terra", "gpt-5.6-sol"),
        "independent_review": ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
        "fast_verification": ("gpt-5.6-luna", "gpt-5.6-terra"),
        "security_review": ("gpt-5.6-terra", "gpt-5.6-sol"),
        "integration_high": ("gpt-5.6-terra", "gpt-5.6-sol"),
    },
}

_EFFORT = {
    "deep_reasoning": "high",
    "strong_coding": "high",
    "architecture_high": "high",
    "independent_review": "medium",
    "fast_verification": "low",
    "security_review": "high",
    "integration_high": "high",
}


class ModelRouter:
    """Resolve role capabilities to model preference lists.

    The runtime talks in capabilities, not vendor model names. This keeps agent
    identities stable when providers add/retire models and lets local overrides
    replace any recommendation without changing profile logic.
    """

    @staticmethod
    def resolve(provider: str, capability: str, policy: str = "balanced") -> ModelPlan:
        policy = policy if policy in {"quality", "balanced", "economy"} else "balanced"
        capability = capability or "strong_coding"
        if provider == "claude":
            table = _CLAUDE[policy]
        elif provider == "codex":
            table = _OPENAI[policy]
        else:
            return ModelPlan(provider, capability, policy, None, (), _EFFORT.get(capability, "medium"))
        candidates = table.get(capability) or table["strong_coding"]
        return ModelPlan(
            provider=provider,
            capability=capability,
            policy=policy,
            recommended=candidates[0] if candidates else None,
            candidates=tuple(candidates),
            effort=_EFFORT.get(capability, "medium"),
        )
