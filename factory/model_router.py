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


# Claude Code documents the durable aliases `opus` and `sonnet`. Prefer those
# rather than pinning a dated model id. This keeps the architecture stable while
# allowing Claude Code to map the alias to the current model exposed by the
# user's subscription. LITE intentionally preserves the proven split: strong
# producer side with Opus, fresh independent evaluator with Sonnet.
_CLAUDE: dict[str, dict[str, tuple[str, ...]]] = {
    "quality": {
        "deep_reasoning": ("opus", "sonnet"),
        "strong_coding": ("opus", "sonnet"),
        "architecture_high": ("opus", "sonnet"),
        "independent_review": ("sonnet", "opus"),
        "fast_verification": ("sonnet", "opus"),
        "security_review": ("opus", "sonnet"),
        "integration_high": ("opus", "sonnet"),
    },
    "balanced": {
        "deep_reasoning": ("opus", "sonnet"),
        "strong_coding": ("opus", "sonnet"),
        "architecture_high": ("opus", "sonnet"),
        "independent_review": ("sonnet", "opus"),
        "fast_verification": ("sonnet", "opus"),
        "security_review": ("opus", "sonnet"),
        "integration_high": ("opus", "sonnet"),
    },
    "economy": {
        "deep_reasoning": ("sonnet", "opus"),
        "strong_coding": ("sonnet", "opus"),
        "architecture_high": ("sonnet", "opus"),
        "independent_review": ("sonnet",),
        "fast_verification": ("sonnet",),
        "security_review": ("sonnet", "opus"),
        "integration_high": ("sonnet", "opus"),
    },
}

# GPT-5.6 tiers are available in Codex on eligible plans. Sol is the highest
# capability tier, Terra balances capability/speed, and Luna is the fast tier.
# A model-selection/access error falls back safely; ordinary execution errors do
# not replay the task on another model.
_OPENAI: dict[str, dict[str, tuple[str, ...]]] = {
    "quality": {
        "deep_reasoning": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
        "strong_coding": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
        "architecture_high": ("gpt-5.6-sol", "gpt-5.6-terra"),
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
    """Resolve stable agent capabilities to provider-specific model preferences."""

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
