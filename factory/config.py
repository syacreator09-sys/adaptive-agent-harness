from __future__ import annotations
import copy, json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "execution": {"profile": "auto", "domain": "code", "max_lite_passes": 3, "max_pro_passes": 5},
    "guardian": {"mode": "auto"},
    "providers": {"strategy": "auto", "prefer_cross_provider_verification": True},
    "billing": {"mode": "subscription_only", "api_fallback": False},
    "models": {"policy": "balanced", "overrides": {}},
    "tools": {"strategy": "adaptive", "allow_missing_optional": True},
    "project": {"preserve_existing_structure": True, "baseline_before_changes": True},
}

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def _read_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
            value = yaml.safe_load(text)
            return value if isinstance(value, dict) else {}
        except Exception as exc:
            raise ValueError(f"Cannot parse {path}; use JSON-compatible YAML or install PyYAML") from exc

@dataclass
class AAHConfig:
    data: dict[str, Any]

    @classmethod
    def load(cls, target: Path | str) -> "AAHConfig":
        target = Path(target)
        path = target / ".aah" / "factory.local.yaml"
        local = _read_yaml_or_json(path) if path.exists() else {}
        return cls(_deep_merge(DEFAULT_CONFIG, local))

    def save(self, target: Path | str) -> Path:
        target = Path(target)
        path = target / ".aah" / "factory.local.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
