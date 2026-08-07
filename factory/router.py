from __future__ import annotations
import re
from typing import Any
from .models import RouteDecision

class AdaptiveRouter:
    def __init__(self, providers: dict[str,dict[str,Any]]): self.providers=providers

    def score(self, request: str) -> tuple[int,int,list[str]]:
        text=request.lower(); complexity=10; risk=5; reasons=[]
        complex_terms={"architecture":20,"multi-service":30,"platform":30,"factory":30,"migration":20,"refactor":20,"dashboard":10,"database":15,"api":10,"full":15,"complete":15}
        risk_terms={"production":45,"prod":35,"payment":35,"billing":30,"auth":30,"authentication":30,"delete":35,"migration":20,"database":15,"secret":25,"credential":25,"vps":20,"dns":25}
        for term,points in complex_terms.items():
            if term in text: complexity += points; reasons.append(f"complex:{term}")
        for term,points in risk_terms.items():
            if term in text: risk += points; reasons.append(f"risk:{term}")
        if len(text)>500: complexity += 20
        elif len(text)>200: complexity += 10
        return min(100,complexity),min(100,risk),reasons

    def route(self, request: str, complexity_hint: int|None=None, risk_hint: int|None=None) -> dict[str,Any]:
        c,r,reasons=self.score(request)
        if complexity_hint is not None: c=complexity_hint
        if risk_hint is not None: r=risk_hint
        profile="lite" if c<=25 else "pro" if c<=70 else "factory"
        guardian="open" if r<30 else "guarded" if r<70 else "locked"
        return RouteDecision(profile,guardian,c,r,reasons).to_dict()

    def available(self) -> list[str]:
        # Installed but explicitly logged-out providers are not schedulable. Unknown auth stays eligible for CLIs without a reliable status probe.
        return [k for k,v in self.providers.items() if v.get("available") and v.get("authenticated") is not False]

    def assign_roles(self, roles: list[str], policy: str="balanced", overrides: dict[str,Any]|None=None) -> dict[str,dict[str,Any]]:
        overrides=overrides or {}; available=self.available()
        if not available: return {r:{"provider":"none","model":None} for r in roles}
        result={}; builder_provider=None
        for role in roles:
            if role in overrides:
                result[role]=dict(overrides[role]); continue
            if role in {"builder","fixer","worker","integrator"}:
                provider="codex" if "codex" in available else available[0]; builder_provider=provider
            elif role in {"evaluator","tester","security_reviewer","final_reviewer","system_tester"} and len(available)>1 and builder_provider:
                provider=next(x for x in available if x!=builder_provider)
            else:
                provider="claude" if "claude" in available else available[0]
            model=self._model_for(provider,role,policy)
            result[role]={"provider":provider,"model":model}
        # Ensure evaluator differs from builder when dual providers, independent of ordering.
        if "builder" in result and "evaluator" in result and len(available)>1 and result["builder"]["provider"]==result["evaluator"]["provider"]:
            result["evaluator"]["provider"]=next(x for x in available if x!=result["builder"]["provider"])
            result["evaluator"]["model"]=self._model_for(result["evaluator"]["provider"],"evaluator",policy)
        return result

    @staticmethod
    def _model_for(provider: str, role: str, policy: str) -> str|None:
        if provider=="claude":
            if policy=="quality" and role in {"planner","architect","security_reviewer","final_reviewer"}: return "opus"
            return "sonnet"
        # Leave Codex model unset so the user's current subscription/default CLI model is used.
        return None
