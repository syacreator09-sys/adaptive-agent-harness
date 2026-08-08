from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path
from typing import Any, Iterable

SECRET_KEY = re.compile(r"(^|_)(api_?key|token|secret|password|passwd|private_?key|credential|cookie|session)(_|$)", re.I)
INLINE_SECRET_PATTERNS=[
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|credential)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
]


def _known_secret_values(extra: Iterable[str] | None=None) -> list[str]:
    values=[]
    for key,value in os.environ.items():
        if value and SECRET_KEY.search(key) and len(value)>=4:
            values.append(value)
    for value in extra or []:
        if value and len(str(value))>=4:
            values.append(str(value))
    return sorted(set(values),key=len,reverse=True)


def redact_text(text: str, known_values: Iterable[str] | None=None) -> str:
    out=str(text)
    for value in _known_secret_values(known_values):
        out=out.replace(value,"[REDACTED]")
    for pattern in INLINE_SECRET_PATTERNS:
        if pattern.groups>=2:
            out=pattern.sub(lambda m:f"{m.group(1)}=[REDACTED]",out)
        else:
            out=pattern.sub("[REDACTED]",out)
    return out


def redact_data(value: Any, known_values: Iterable[str] | None=None) -> Any:
    secrets=_known_secret_values(known_values)
    if isinstance(value,dict):
        clean={}
        for key,item in value.items():
            if SECRET_KEY.search(str(key)):
                clean[key]="[REDACTED]"
            else:
                clean[key]=redact_data(item,secrets)
        return clean
    if isinstance(value,list):
        return [redact_data(item,secrets) for item in value]
    if isinstance(value,tuple):
        return [redact_data(item,secrets) for item in value]
    if isinstance(value,str):
        return redact_text(value,secrets)
    return value


def redact(text: str) -> str:
    return redact_text(text)


class EvidenceStore:
    def __init__(self, run_dir: Path):
        self.run_dir=Path(run_dir)
        self.path=self.run_dir/"EVIDENCE.jsonl"

    def append(self, record: dict[str,Any]) -> None:
        if not isinstance(record, dict):
            record={"type":"invalid_evidence_record","detail":str(record),"ok":False}
        safe=redact_data(record)
        if not safe.get("id"):
            safe=dict(safe)
            safe["id"]="E-auto-"+hashlib.sha256(
                json.dumps(safe,sort_keys=True,default=str).encode("utf-8")
            ).hexdigest()[:12]
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(safe,sort_keys=True,default=str)+"\n")

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
