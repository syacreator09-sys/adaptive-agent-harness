from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    pass


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_rubric(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("criteria", value.get("items", []))
    if not isinstance(value, list):
        raise ContractError("RUBRIC.json must be an array or an object with criteria[]")

    criteria: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ContractError(f"rubric criterion {index} must be an object")
        criterion_id = str(raw.get("id") or "").strip()
        if not criterion_id:
            raise ContractError(f"rubric criterion {index} is missing id")
        if criterion_id in seen:
            raise ContractError(f"duplicate rubric id {criterion_id}")
        seen.add(criterion_id)
        description = str(raw.get("criterion") or raw.get("description") or raw.get("expected") or "").strip()
        if not description:
            raise ContractError(f"rubric criterion {criterion_id} is missing a binary criterion/description")
        required = bool(raw.get("required", True))
        item: dict[str, Any] = {
            "id": criterion_id,
            "required": required,
            "criterion": description,
        }
        verification = raw.get("verification") or raw.get("verify")
        if verification:
            item["verification"] = verification
        criteria.append(item)

    if not criteria:
        raise ContractError("rubric must contain at least one criterion")
    if not any(item["required"] for item in criteria):
        raise ContractError("rubric must contain at least one required criterion")
    return criteria


def status_from_baseline(criteria: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "criteria": [
            {
                "id": item["id"],
                "status": "UNVERIFIED",
                "evidence": [],
            }
            for item in criteria
        ]
    }


def seal_contract(run_dir: Path) -> dict[str, Any]:
    """Seal Planner outputs into an immutable acceptance baseline.

    Planner writes SPEC.md + RUBRIC.json. The runtime owns RUBRIC_BASELINE.json,
    RUBRIC_STATUS.json and CONTRACT.json. Once CONTRACT.json exists, sealing is
    idempotent and any baseline/spec mutation is detected instead of accepted.
    """
    run_dir = Path(run_dir)
    spec_path = run_dir / "SPEC.md"
    rubric_path = run_dir / "RUBRIC.json"
    baseline_path = run_dir / "RUBRIC_BASELINE.json"
    status_path = run_dir / "RUBRIC_STATUS.json"
    contract_path = run_dir / "CONTRACT.json"

    if not spec_path.exists():
        raise ContractError("Planner did not produce SPEC.md")
    spec = spec_path.read_text(encoding="utf-8").strip()
    if not spec:
        raise ContractError("SPEC.md is empty")
    if not rubric_path.exists():
        raise ContractError("Planner did not produce RUBRIC.json")

    try:
        draft = json.loads(rubric_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContractError("RUBRIC.json is not valid JSON") from exc
    criteria = normalize_rubric(draft)
    baseline = {"criteria": criteria}
    baseline_text = json.dumps(baseline, indent=2, sort_keys=True) + "\n"
    spec_text = spec + "\n"
    expected = {
        "version": 1,
        "spec_sha256": _sha256_text(spec_text),
        "rubric_sha256": _sha256_text(baseline_text),
        "required_criteria": sum(1 for item in criteria if item["required"]),
        "total_criteria": len(criteria),
    }

    if contract_path.exists():
        try:
            current = json.loads(contract_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ContractError("CONTRACT.json is corrupt") from exc
        if current.get("spec_sha256") != expected["spec_sha256"]:
            raise ContractError("SPEC.md changed after contract sealing")
        if not baseline_path.exists():
            raise ContractError("sealed contract is missing RUBRIC_BASELINE.json")
        actual_baseline = baseline_path.read_text(encoding="utf-8")
        if _sha256_text(actual_baseline) != current.get("rubric_sha256"):
            raise ContractError("RUBRIC_BASELINE.json changed after contract sealing")
        return current

    baseline_path.write_text(baseline_text, encoding="utf-8")
    status_path.write_text(json.dumps(status_from_baseline(criteria), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    contract_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return expected


def verify_contract(run_dir: Path) -> tuple[bool, list[str]]:
    run_dir = Path(run_dir)
    failures: list[str] = []
    contract_path = run_dir / "CONTRACT.json"
    baseline_path = run_dir / "RUBRIC_BASELINE.json"
    spec_path = run_dir / "SPEC.md"
    if not contract_path.exists():
        return False, ["contract:missing"]
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception:
        return False, ["contract:invalid_json"]
    if not spec_path.exists():
        failures.append("contract:spec_missing")
    else:
        spec_text = spec_path.read_text(encoding="utf-8")
        if _sha256_text(spec_text) != contract.get("spec_sha256"):
            failures.append("contract:spec_hash_mismatch")
    if not baseline_path.exists():
        failures.append("contract:rubric_baseline_missing")
    else:
        baseline_text = baseline_path.read_text(encoding="utf-8")
        if _sha256_text(baseline_text) != contract.get("rubric_sha256"):
            failures.append("contract:rubric_hash_mismatch")
        try:
            normalize_rubric(json.loads(baseline_text))
        except Exception:
            failures.append("contract:rubric_baseline_invalid")
    return not failures, failures


def baseline_criteria(run_dir: Path) -> list[dict[str, Any]]:
    path = Path(run_dir) / "RUBRIC_BASELINE.json"
    if not path.exists():
        return []
    try:
        return normalize_rubric(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return []


def status_map(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = Path(run_dir) / "RUBRIC_STATUS.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = value.get("criteria", value) if isinstance(value, dict) else value
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if isinstance(raw, dict) and raw.get("id"):
            out[str(raw["id"])] = raw
    return out
