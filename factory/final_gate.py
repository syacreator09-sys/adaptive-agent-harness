from __future__ import annotations
from pathlib import Path
from typing import Any
from .evidence import EvidenceStore

class FinalGate:
    def __init__(self, run_dir: Path): self.run_dir=Path(run_dir)
    def evaluate(self, rubric: list[dict[str,Any]], findings: list[dict[str,Any]], mandatory_gates: list[dict[str,Any]]|None=None) -> dict[str,Any]:
        evidence_ids=EvidenceStore(self.run_dir).ids(); failures=[]
        for item in rubric:
            if not item.get("required",True): continue
            status=str(item.get("status","UNVERIFIED")).upper()
            if status!="PASS": failures.append(f"{item.get('id')}:status={status}")
            refs=item.get("evidence") or []
            if not refs: failures.append(f"{item.get('id')}:missing_evidence")
            elif any(str(x) not in evidence_ids for x in refs): failures.append(f"{item.get('id')}:invalid_evidence")
        for f in findings:
            if str(f.get("status","open")).lower()=="open" and str(f.get("severity","")).lower() in {"critical","major"}:
                failures.append(f"{f.get('id')}:open_{f.get('severity')}")
        for gate in mandatory_gates or []:
            if not gate.get("ok",False): failures.append(f"gate:{gate.get('name','unknown')}")
        return {"done":not failures,"failures":failures,"required":sum(1 for x in rubric if x.get("required",True)),"passed":sum(1 for x in rubric if x.get("required",True) and str(x.get("status","")).upper()=="PASS")}
