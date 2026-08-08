from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class EventJournal:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "EVENTS.jsonl"

    def append(self, event: str, **data: Any) -> dict[str, Any]:
        record = {
            "at": datetime.now().astimezone().isoformat(),
            "event": event,
            **data,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            handle.flush()
        return record

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            except Exception:
                rows.append({"event": "JOURNAL_CORRUPT", "raw": line[:500]})
        return rows
