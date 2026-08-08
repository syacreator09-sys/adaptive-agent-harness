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


# Preference orders, not availability claims. AAH falls back only on explicit
# model-selection/access errors. Claude Code's own /model remains source of truth
# for a given account; the ids below are current documented choices.
_CLAUDE: dict[str, dict[str, tuple[str, ...]]] = {
    "quality": {
        "deep_reasoning": ("claude-opus-4-8", "claude-sonnet-5"),
        "strong_coding": ("claude-opus-4-8", "claude-sonnet-5"),
        "architecture_high": ("claude-opus-4-8", "claude-sonnet-5"),
        "independent_review": ("claude-sonnet-5", "claude-opus-4-8"),
        "fast_verification": ("claude-sonnet-5", "claude-opus-4-8"),
        "security_review": ("claude-opus-4-8", "claude-sonnet-5"),
        "integration_high": ("claude-opus-4-8", "claude-sonnet-5"),
    },
    "balanced": {
        # LITE intentionally mirrors the proven split: high-reasoning producer
        # side, then a fresh Sonnet-family evaluator.
        "deep_reasoning": ("claude-opus-4-8", "claude-sonnet-5"),
        "strong_coding": ("claude-opus-4-8", "claude-sonnet-5"),
        "architecture_high": ("claude-opus-4-8", "claude-sonnet-5"),
        "independent_review": ("claude-sonnet-5", "claude-opus-4-8"),
        "fast_verification": ("claude-sonnet-5", "claude-opus-4-8"),
        "security_review": ("claude-opus-4-8", "claude-sonnet-5"),
        "integration_high": ("claude-opus-4-8", "claude-sonnet-5"),
    },
    "economy": {
        "deep_reasoning": ("claude-sonnet-5", "claude-opus-4-8"),
        "strong_coding": ("claude-sonnet-5", "claude-opus-4-8"),
        "architecture_high": ("claude-sonnet-5", "claude-opus-4-8"),
        "independent_review": ("claude-sonnet-5",),
        "fast_verification": ("claude-sonnet-5",),
        "security_review": ("claude-sonnet-5", "claude-opus-4-8"),
        "integration_high": ("claude-sonnet-5", "claude-opus-4-8"),
    },
}

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
