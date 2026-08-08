from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


_SECRET_KEY = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|private|credential|cookie|authorization|database[_-]?url|dsn|jwt|session[_-]?(?:token|secret|key|cookie))",
    re.I,
)
_INLINE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]{12,}"),
]


def _known_secret_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if value and len(value) >= 8 and _SECRET_KEY.search(key):
            values.append(value)
    return sorted(set(values), key=len, reverse=True)


def redact_text(text: str) -> str:
    out = str(text)
    for value in _known_secret_values():
        out = out.replace(value, "[REDACTED]")
    for pattern in _INLINE_PATTERNS:
        if pattern.groups:
            out = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", out)
        else:
            out = pattern.sub("[REDACTED]", out)
    return out


def redact_data(value: Any, key: str | None = None) -> Any:
    # Audit identifiers such as `session`/`session_id` are intentionally kept;
    # credentials named session_token/session_secret are not.
    if key and _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_data(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(v) for v in value]
    if isinstance(value, tuple):
        return [redact_data(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class EvidenceStore:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "EVIDENCE.jsonl"

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            record = {
                "type": "invalid_evidence_record",
                "ok": False,
                "detail": str(record),
            }
        safe = redact_data(dict(record))
        if not safe.get("id"):
            digest = hashlib.sha256(
                json.dumps(safe, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:12]
            safe["id"] = f"E-auto-{digest}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return safe

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for index, line in enumerate(
            self.path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("evidence row is not an object")
                rows.append(value)
            except Exception as exc:
                rows.append({
                    "id": f"E-invalid-line-{index}",
                    "type": "invalid_evidence_jsonl",
                    "ok": False,
                    "_invalid": True,
                    "line": index,
                    "error": type(exc).__name__,
                })
        return rows

    def ids(self) -> set[str]:
        return {str(item.get("id")) for item in self.all() if item.get("id")}
