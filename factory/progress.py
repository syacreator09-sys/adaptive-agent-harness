from __future__ import annotations
from typing import Any
from .final_gate import normalize_rubric


class ProgressDetector:
    @staticmethod
    def score(rubric: Any) -> tuple[int,int]:
        items=normalize_rubric(rubric)
        required=[x for x in items if x.get("required",True)]
        passed=sum(1 for x in required if str(x.get("status","")).upper()=="PASS")
        return passed,len(required)

    def assess(self, history: list[dict[str,Any]]) -> dict[str,Any]:
        if len(history)<2:
            return {"stalled":False,"regressed":False}
        prev,cur=history[-2],history[-1]
        pprev=prev.get("passed",0); pcur=cur.get("passed",0)
        return {
            "stalled":pcur<=pprev and cur.get("open_findings",0)>=prev.get("open_findings",0),
            "regressed":pcur<pprev,
        }
