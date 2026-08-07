from __future__ import annotations
from typing import Any
from .models import RouteDecision

class AdaptiveRouter:
    def __init__(self,providers:dict[str,dict[str,Any]]): self.providers=providers
    def score(self,request:str):
        text=request.lower(); complexity=10; risk=5; reasons=[]
        complex_terms={"architecture":20,"multi-service":30,"platform":30,"factory":30,"migration":20,"refactor":20,"dashboard":10,"database":15,"api":10,"full":15,"complete":15}
        risk_terms={"production":45,"prod":35,"payment":35,"billing":30,"auth":30,"authentication":30,"delete":35,"migration":20,"database":15,"secret":25,"credential":25,"vps":20,"dns":25}
        for term,points in complex_terms.items():
            if term in text: complexity+=points; reasons.append(f"complex:{term}")
        for term,points in risk_terms.items():
            if term in text: risk+=points; reasons.append(f"risk:{term}")
        if len(text)>500: complexity+=20
        elif len(text)>200: complexity+=10
        return min(100,complexity),min(100,risk),reasons
    def route(self,request,complexity_hint=None,risk_hint=None):
        c,r,reasons=self.score(request); c=complexity_hint if complexity_hint is not None else c; r=risk_hint if risk_hint is not None else r
        profile="lite" if c<=25 else "pro" if c<=70 else "factory"; guardian="open" if r<30 else "guarded" if r<70 else "locked"
        return RouteDecision(profile,guardian,c,r,reasons).to_dict()
    def available(self): return [k for k,v in self.providers.items() if v.get("available")]
    def assign_roles(self,roles,policy="balanced",overrides=None):
        overrides=overrides or {}; available=self.available()
        if not available: return {r:{"provider":"none","model":None} for r in roles}
        result={}; builder_provider=None
        for role in roles:
            if role in overrides: result[role]=dict(overrides[role]); continue
            if role in {"builder","fixer","worker","integrator"}: provider="codex" if "codex" in available else available[0]; builder_provider=provider
            elif role in {"evaluator","tester","security_reviewer","final_reviewer","system_tester"} and len(available)>1 and builder_provider: provider=next(x for x in available if x!=builder_provider)
            else: provider="claude" if "claude" in available else available[0]
            result[role]={"provider":provider,"model":self._model_for(provider,role,policy)}
        if "builder" in result and "evaluator" in result and len(available)>1 and result["builder"]["provider"]==result["evaluator"]["provider"]:
            result["evaluator"]["provider"]=next(x for x in available if x!=result["builder"]["provider"]); result["evaluator"]["model"]=self._model_for(result["evaluator"]["provider"],"evaluator",policy)
        return result
    @staticmethod
    def _model_for(provider,role,policy):
        if provider=="claude":
            if policy=="quality" and role in {"planner","architect","security_reviewer","final_reviewer"}: return "opus"
            return "sonnet"
        return None
