from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any

SECRET_VALUE_PATTERNS=[
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]

def redact(text: str) -> str:
    out=text
    for p in SECRET_VALUE_PATTERNS:
        if p.groups>=2: out=p.sub(lambda m:f"{m.group(1)}=[REDACTED]",out)
        else: out=p.sub("[REDACTED]",out)
    return out

class EvidenceStore:
    def __init__(self, run_dir: Path): self.run_dir=Path(run_dir); self.path=self.run_dir/"EVIDENCE.jsonl"
    def append(self, record: dict[str,Any]) -> None:
        if not record.get("id"): raise ValueError("evidence requires id")
        safe=json.loads(redact(json.dumps(record)))
        with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(safe,sort_keys=True)+"\n")
    def all(self) -> list[dict[str,Any]]:
        if not self.path.exists(): return []
        rows=[]
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip(): rows.append(json.loads(line))
        return rows
    def ids(self) -> set[str]: return {str(x.get("id")) for x in self.all()}
