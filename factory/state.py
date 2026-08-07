from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any
from .artifacts import ArtifactStore
from .models import Phase

class RunStateStore:
    def __init__(self, run_dir: Path): self.run_dir=Path(run_dir)
    def load(self) -> dict[str, Any]: return ArtifactStore.read_json(self.run_dir,"STATE.json",{})
    def save(self, state: dict[str, Any]) -> None: ArtifactStore(self.run_dir.parents[2]).write_json(self.run_dir,"STATE.json",state)
    def transition(self, phase: Phase | str, **updates: Any) -> dict[str, Any]:
        state=self.load(); phase_value=phase.value if isinstance(phase,Phase) else str(phase)
        state.setdefault("history",[]).append({"from":state.get("phase"),"to":phase_value,"at":datetime.now().astimezone().isoformat()})
        state["phase"]=phase_value; state.update(updates); self.save(state); return state
