from __future__ import annotations
from pathlib import Path
from typing import Any
from .evidence import EvidenceStore


def normalize_rubric(rubric: Any) -> list[dict[str, Any]]:
    if isinstance(rubric, dict):
        rubric = rubric.get("criteria", rubric.get("items", []))
    if not isinstance(rubric, list):
        return []
    return [item if isinstance(item, dict) else {"id": str(item), "status": "UNVERIFIED"} for item in rubric]


def normalize_findings(findings: Any) -> list[dict[str, Any]]:
    if isinstance(findings, dict):
        findings = findings.get("findings", findings.get("items", []))
    if not isinstance(findings, list):
        return []
    return [item if isinstance(item, dict) else {"id": str(item), "severity": "major", "status": "open"} for item in findings]


def _evidence_refs(item: dict[str, Any]) -> list[str]:
    raw = item.get("evidence")
    if raw in (None, "", []):
        raw = item.get("evidence_ref")
    if raw in (None, "", []):
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple, set)):
        return [str(x) for x in raw if x not in (None, "")]
    return [str(raw)]


class FinalGate:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)

    def evaluate(self, rubric: Any, findings: Any, mandatory_gates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        rubric_items = normalize_rubric(rubric)
        finding_items = normalize_findings(findings)
        records = EvidenceStore(self.run_dir).all()
        failures: list[str] = []

        if not rubric_items:
            failures.append("rubric:missing_or_invalid")

        required_items=[item for item in rubric_items if item.get("required",True)]
        if rubric_items and not required_items:
            failures.append("rubric:no_required_criteria")

        if any(bool(record.get("_invalid")) for record in records):
            failures.append("evidence:invalid_jsonl")

        by_ref: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            for ref in (record.get("id"), record.get("type")):
                if ref not in (None, ""):
                    by_ref.setdefault(str(ref), []).append(record)

        for item in required_items:
            item_id = item.get("id", "unknown")
            status = str(item.get("status", "UNVERIFIED")).upper()
            if status != "PASS":
                failures.append(f"{item_id}:status={status}")

            refs = _evidence_refs(item)
            if not refs:
                failures.append(f"{item_id}:missing_evidence")
                continue

            for ref in refs:
                matched = by_ref.get(ref, [])
                if not matched:
                    failures.append(f"{item_id}:invalid_evidence:{ref}")
                    continue
                if any(record.get("ok") is False for record in matched):
                    failures.append(f"{item_id}:failed_evidence:{ref}")
                    continue
                if not any(record.get("ok") is True for record in matched):
                    failures.append(f"{item_id}:unverified_evidence:{ref}")

        for finding in finding_items:
            if str(finding.get("status", "open")).lower() == "open" and str(finding.get("severity", "")).lower() in {"critical", "major"}:
                failures.append(f"{finding.get('id')}:open_{finding.get('severity')}")

        for gate in mandatory_gates or []:
            if gate.get("ok") is not True:
                failures.append(f"gate:{gate.get('name', 'unknown')}")

        failures = list(dict.fromkeys(failures))
        required = len(required_items)
        passed = sum(1 for item in required_items if str(item.get("status", "")).upper() == "PASS")
        return {"done": not failures, "failures": failures, "required": required, "passed": passed}
