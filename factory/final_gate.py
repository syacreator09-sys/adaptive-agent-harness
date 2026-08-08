from __future__ import annotations
from pathlib import Path
from typing import Any
from .evidence import EvidenceStore

# Across 3 real evaluator runs (2026-08-07, RUN-004/006/007/008) the exact
# same semantic field came back under 4 different names for evidence
# pointers and 2 for the pass/fail verdict -- none pinned anywhere in
# agents.py or .claude/agents/*.md, so a fresh evaluator invents a
# plausible-sounding name each time. Aliased here as a safety net;
# .claude/agents/aah-evaluator.md now also pins the canonical shape so
# future runs converge instead of the alias list growing forever.
_EVIDENCE_KEYS = ("evidence", "evidence_ref", "evidence_refs", "evidence_ids")
_STATUS_KEYS = ("status", "verdict")

def _normalize_item(item: dict[str,Any]) -> dict[str,Any]:
    item = dict(item)
    for key in _STATUS_KEYS:
        if item.get(key): item["status"] = item[key]; break
    for key in _EVIDENCE_KEYS:
        if item.get(key): item["evidence"] = item[key]; break
    return item

def _normalize_rubric(rubric: Any) -> list[dict[str,Any]]:
    # Neither agents.py nor the .claude/agents/*.md contracts pin down
    # RUBRIC.json's exact top-level shape -- confirmed live (plan
    # AUTONOMÍA TOTAL, 2026-08-07, RUN-20260807-004): a real evaluator
    # wrote {"criteria": [...], "overall_verdict": ..., ...} instead of
    # a bare list, and `for item in rubric` iterated the dict's string
    # KEYS, crashing the whole process with AttributeError on
    # item.get(...) -- exactly the "gate crashes instead of failing
    # closed" failure mode already fixed once in evidence.py. Same
    # remedy: normalize known-reasonable shapes, and treat any item
    # that still isn't a dict as an UNVERIFIED criterion rather than
    # raising.
    if isinstance(rubric, dict):
        rubric = rubric.get("criteria", rubric.get("items", []))
    if not isinstance(rubric, list): return []
    return [_normalize_item(item) if isinstance(item, dict) else {"id": str(item), "status": "UNVERIFIED"} for item in rubric]

def _normalize_findings(findings: Any) -> list[dict[str,Any]]:
    # Same unpinned-schema failure class as _normalize_rubric, hit by the
    # very next run after that fix (RUN-20260807-006): a real evaluator
    # wrote FINDINGS.json as one free-form report object (root_cause,
    # notes, verdict, ...) with no "findings"/"items" list at all --
    # `for f in findings` iterated its string keys and crashed with the
    # identical AttributeError. Unlike a rubric criterion (a required,
    # countable check -- an unparseable one must fail-closed as
    # UNVERIFIED), an unparseable FINDINGS.json carries no severity to
    # honestly report, so it degrades to "no additional findings logged"
    # rather than inventing a blocking one; RUBRIC.json stays the
    # authoritative PASS/FAIL source either way.
    if isinstance(findings, dict):
        findings = findings.get("findings", findings.get("items", []))
    if not isinstance(findings, list): return []
    return [f for f in findings if isinstance(f, dict)]

class FinalGate:
    def __init__(self, run_dir: Path): self.run_dir=Path(run_dir)
    def evaluate(self, rubric: list[dict[str,Any]], findings: list[dict[str,Any]], mandatory_gates: list[dict[str,Any]]|None=None) -> dict[str,Any]:
        rubric=_normalize_rubric(rubric)
        findings=_normalize_findings(findings)
        records=EvidenceStore(self.run_dir).all()
        failures=[]
        # Same unresolved-schema gap as the rubric shape above: nothing
        # documents whether a criterion's evidence pointer is the
        # EvidenceStore's own "id" or the evidence record's semantic
        # "type" -- a real evaluator run referenced evidence by "type"
        # (e.g. "unittest_run"), which is legitimately admissible (it
        # resolves to a real, redacted EVIDENCE.jsonl record) even
        # though it isn't a literal "id" match.
        evidence_refs={str(r.get("id")) for r in records} | {str(r.get("type")) for r in records if r.get("type")}
        for item in rubric:
            if not item.get("required",True): continue
            status=str(item.get("status","UNVERIFIED")).upper()
            if status!="PASS": failures.append(f"{item.get('id')}:status={status}")
            refs=item.get("evidence") or []
            if not refs: failures.append(f"{item.get('id')}:missing_evidence")
            elif any(str(x) not in evidence_refs for x in refs): failures.append(f"{item.get('id')}:invalid_evidence")
        for f in findings:
            if str(f.get("status","open")).lower()=="open" and str(f.get("severity","")).lower() in {"critical","major"}:
                failures.append(f"{f.get('id')}:open_{f.get('severity')}")
        for gate in mandatory_gates or []:
            if not gate.get("ok",False): failures.append(f"gate:{gate.get('name','unknown')}")
        return {"done":not failures,"failures":failures,"required":sum(1 for x in rubric if x.get("required",True)),"passed":sum(1 for x in rubric if x.get("required",True) and str(x.get("status","")).upper()=="PASS")}
