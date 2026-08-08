from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any

SECRET_VALUE_PATTERNS=[
    # redact() runs on json.dumps(record) (see append() below), so a
    # matched value is always inside a JSON string -- the old character
    # class ([^\s,;]+) did not stop at the value's closing quote, so a
    # secret-looking value with no trailing whitespace/comma (e.g. the
    # last field in an object) consumed the closing '"' and even a
    # following '}'/']', corrupting the JSON and making json.loads()
    # raise (confirmed live: a real evidence record with
    # "detail": "api_key=sk-..." at the end of the object crashed here).
    # '"', '}' and ']' are JSON structural terminators in this context,
    # so they end the match same as whitespace/comma/semicolon already did.
    re.compile(r'(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;"}\]]+)'),
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
    def append(self, record: dict[str,Any] | str) -> None:
        # A fresh agent occasionally returns a real, usable evidence
        # record without remembering the "id" field the RUBRIC->EVIDENCE
        # cross-reference needs -- that used to hard-crash the whole run
        # (ValueError propagating out of profiles/common.py::_ingest,
        # uncaught, leaving STATE.json stuck mid-phase with no recorded
        # failure -- confirmed live). The evidence content itself is not
        # fabricated or altered; a stable id is derived from it (sha256 of
        # the redacted JSON, truncated) so re-ingesting the identical
        # record twice yields the identical id instead of a random one
        # each time, which would otherwise let the same evidence silently
        # multiply under different ids.
        #
        # Found live at PRO scale (plan AUTONOMÍA TOTAL A6, 2026-08-08,
        # first-ever real PRO run against cano-hermes-agentic-os,
        # RUN-20260808-001): a PRO evaluator's "evidence" list contained a
        # bare string, not an object -- `record.get("id")` crashed with
        # AttributeError before ever reaching the missing-id fallback
        # above, the exact same "gate/ingest crashes instead of
        # degrading" failure class already fixed twice elsewhere
        # (evidence-id itself, and final_gate.py's rubric/findings
        # normalization) but never here at the entry point. A bare string
        # is real content an agent wanted recorded (e.g. "confirmed no
        # hardcoded secrets in config.py") -- worth keeping, not
        # discarding, so it's wrapped rather than dropped.
        if not isinstance(record, dict):
            record = {"detail": str(record)}
        if not record.get("id"):
            record = dict(record)
            record["id"] = "E-auto-" + hashlib.sha256(
                json.dumps(record, sort_keys=True).encode("utf-8")
            ).hexdigest()[:12]
        safe=json.loads(redact(json.dumps(record)))
        with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(safe,sort_keys=True)+"\n")
    def all(self) -> list[dict[str,Any]]:
        if not self.path.exists(): return []
        rows=[]
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip(): rows.append(json.loads(line))
        return rows
    def ids(self) -> set[str]: return {str(x.get("id")) for x in self.all()}
