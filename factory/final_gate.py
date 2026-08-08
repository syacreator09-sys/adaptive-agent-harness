from __future__ import annotations
from pathlib import Path
from typing import Any
from .contracts import baseline_criteria, validated_status_map, verify_contract
from .evidence import EvidenceStore


def normalize_findings(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("findings", value.get("items", []))
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


class FinalGate:
    """Fail-closed deterministic completion gate.

    Required acceptance criteria are read only from the sealed runtime contract.
    Evaluator status must be a valid snapshot of that contract. Criterion proof
    references stable evidence IDs only; semantic evidence types are reserved for
    mandatory technical/system/security gates.
    """

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)

    def evaluate(
        self,
        rubric: Any = None,
        findings: Any = None,
        mandatory_gates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del rubric
        failures: list[str] = []
        if not (self.run_dir / "CONTRACT.json").exists():
            return {
                "done": False,
                "failures": ["contract:missing"],
                "required": 0,
                "passed": 0,
                "contract_sealed": False,
            }

        contract_ok, contract_failures = verify_contract(self.run_dir)
        if not contract_ok:
            failures.extend(contract_failures)
        criteria = baseline_criteria(self.run_dir)
        statuses, status_failures = validated_status_map(self.run_dir, criteria)
        failures.extend(status_failures)

        required = [item for item in criteria if item.get("required", True)]
        if not criteria:
            failures.append("rubric:missing_or_invalid")
        if criteria and not required:
            failures.append("rubric:no_required_criteria")

        records = EvidenceStore(self.run_dir).all()
        if any(record.get("_invalid") for record in records):
            failures.append("evidence:invalid_jsonl")

        by_id: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            evidence_id = record.get("id")
            if evidence_id not in (None, ""):
                by_id.setdefault(str(evidence_id), []).append(record)
        for evidence_id, matches in by_id.items():
            if len(matches) > 1:
                failures.append(f"evidence:duplicate_id:{evidence_id}")

        passed = 0
        for baseline in required:
            criterion_id = str(baseline.get("id") or "unknown")
            status_row = statuses.get(criterion_id, {})
            status = str(status_row.get("status", "UNVERIFIED")).upper()
            criterion_ok = status == "PASS"
            if not criterion_ok:
                failures.append(f"{criterion_id}:status={status}")

            refs = status_row.get("evidence") or []
            if not refs:
                failures.append(f"{criterion_id}:missing_evidence")
                criterion_ok = False
            else:
                for ref in refs:
                    matched = by_id.get(str(ref), [])
                    if not matched:
                        failures.append(f"{criterion_id}:invalid_evidence:{ref}")
                        criterion_ok = False
                        continue
                    if len(matched) != 1:
                        failures.append(f"{criterion_id}:ambiguous_evidence:{ref}")
                        criterion_ok = False
                        continue
                    record = matched[0]
                    if record.get("ok") is False:
                        failures.append(f"{criterion_id}:failed_evidence:{ref}")
                        criterion_ok = False
                        continue
                    if record.get("ok") is not True:
                        failures.append(f"{criterion_id}:unverified_evidence:{ref}")
                        criterion_ok = False
            if criterion_ok:
                passed += 1

        for finding in normalize_findings(findings or []):
            if (
                str(finding.get("status", "open")).lower() == "open"
                and str(finding.get("severity", "")).lower() in {"critical", "major"}
            ):
                failures.append(f"{finding.get('id', 'finding')}:open_{finding.get('severity')}")

        for gate in mandatory_gates or []:
            if gate.get("ok") is not True:
                failures.append(f"gate:{gate.get('name', 'unknown')}")

        failures = list(dict.fromkeys(failures))
        return {
            "done": not failures,
            "failures": failures,
            "required": len(required),
            "passed": passed,
            "contract_sealed": True,
        }
