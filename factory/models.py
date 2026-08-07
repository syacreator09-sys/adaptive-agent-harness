from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

class Profile(str, Enum):
    AUTO = "auto"
    LITE = "lite"
    PRO = "pro"
    FACTORY = "factory"

class GuardianMode(str, Enum):
    AUTO = "auto"
    OPEN = "open"
    GUARDED = "guarded"
    LOCKED = "locked"

class Phase(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    BUILDING = "building"
    TESTING = "testing"
    EVALUATING = "evaluating"
    FIXING = "fixing"
    INTEGRATING = "integrating"
    REVIEWING = "reviewing"
    DONE = "done"
    PAUSED = "paused"
    FAILED = "failed"

@dataclass
class RunHandle:
    run_id: str
    run_dir: Any

@dataclass
class RouteDecision:
    profile: str
    guardian: str
    complexity_score: int
    risk_score: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
