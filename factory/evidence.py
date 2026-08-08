from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any

SECRET_VALUE_PATTERNS=[
    re.compile(r'(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;"}\]]+)'),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]


def redact(text: str) -> str:
    out=text
    for p in SECRET_VALUE_PATTERNS:
        if p.groups>=2:
            out=p.sub(lambda m:f"{m.group(1)}=[REDACTED]",out)
        else:
            out=p.sub("[REDACTED]",out)
    return out


class EvidenceStore:
    def __init__(self, run_dir: Path):
        self.run_dir=Path(run_dir)
        self.path=self.run_dir/"EVIDENCE.jsonl"

    def append(self, record: dict[str,Any]) -> None:
        if not isinstance(record, dict):
            record={"type":"invalid_evidence_record","detail":str(record),"ok":False}
        if not record.get("id"):
            record=dict(record)
            record["id"]="E-auto-"+hashlib.sha256(
                json.dumps(record,sort_keys=True,default=str).encode("utf-8")
            ).hexdigest()[:12]
        safe=json.loads(redact(json.dumps(record,default=str)))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(safe,sort_keys=True)+"\n")

    def all(self) -> list[dict[str,Any]]:
        if not self.path.exists():
            return []
        rows=[]
        for index,line in enumerate(self.path.read_text(encoding="utf-8",errors="replace").splitlines(),start=1):
            if not line.strip():
                continue
            try:
                value=json.loads(line)
                if not isinstance(value,dict):
                    raise ValueError("evidence row is not an object")
                rows.append(value)
            except Exception as exc:
                # Fail closed without crashing the whole run. FinalGate sees _invalid and blocks DONE.
                rows.append({
                    "id":f"E-invalid-line-{index}",
                    "type":"invalid_evidence_jsonl",
                    "ok":False,
                    "_invalid":True,
                    "line":index,
                    "error":type(exc).__name__,
                })
        return rows

    def ids(self) -> set[str]:
        return {str(x.get("id")) for x in self.all() if x.get("id")}
