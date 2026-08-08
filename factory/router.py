from __future__ import annotations
from typing import Any
from .models import RouteDecision


class AdaptiveRouter:
    def __init__(self, providers: dict[str,dict[str,Any]]):
        self.providers=providers

    def score(self, request: str) -> tuple[int,int,list[str]]:
        text=request.lower(); complexity=10; risk=5; reasons=[]
        complex_terms={"architecture":20,"multi-service":30,"platform":30,"factory":30,"migration":20,"refactor":20,"dashboard":10,"database":15,"api":10,"full":15,"complete":15}
        risk_terms={"production":45,"prod":35,"payment":35,"billing":30,"auth":30,"authentication":30,"delete":35,"migration":20,"database":15,"secret":25,"credential":25,"vps":20,"dns":25}
        for term,points in complex_terms.items():
            if term in text:
                complexity += points; reasons.append(f"complex:{term}")
        for term,points in risk_terms.items():
            if term in text:
                risk += points; reasons.append(f"risk:{term}")
        if len(text)>500:
            complexity += 20
        elif len(text)>200:
            complexity += 10
        return min(100,complexity),min(100,risk),reasons

    def route(self, request: str, complexity_hint: int|None=None, risk_hint: int|None=None) -> dict[str,Any]:
        c,r,reasons=self.score(request)
        if complexity_hint is not None:
            c=max(0,min(100,int(complexity_hint)))
        if risk_hint is not None:
            r=max(0,min(100,int(risk_hint)))
        profile="lite" if c<=25 else "pro" if c<=70 else "factory"
        guardian="open" if r<30 else "guarded" if r<70 else "locked"
        return RouteDecision(profile,guardian,c,r,reasons).to_dict()

    def available(self) -> list[str]:
        return [k for k,v in self.providers.items() if v.get("available") and v.get("authenticated") is not False]

    def _default_assignment(self, role: str, policy: str, available: list[str], builder_provider: str|None) -> tuple[dict[str,Any],str|None]:
        if role in {"builder","fixer","worker","integrator","content_producer","researcher"}:
            provider="codex" if "codex" in available else available[0]
            builder_provider=provider
        elif role in {"evaluator","tester","task_evaluator","security_reviewer","final_reviewer","system_tester","content_evaluator","fact_checker"} and len(available)>1 and builder_provider:
            provider=next(x for x in available if x!=builder_provider)
        else:
            provider="claude" if "claude" in available else available[0]
        return {"provider":provider,"model":self._model_for(provider,role,policy)},builder_provider

    def assign_roles(self, roles: list[str], policy: str="balanced", overrides: dict[str,Any]|None=None) -> dict[str,dict[str,Any]]:
        overrides=overrides or {}
        available=self.available()
        if not available:
            return {role:{"provider":"none","model":None} for role in roles}

        result: dict[str,dict[str,Any]]={}
        builder_provider=None
        for role in roles:
            assignment,builder_provider=self._default_assignment(role,policy,available,builder_provider)
            patch=overrides.get(role)
            if patch is not None:
                if not isinstance(patch,dict):
                    raise ValueError(f"Model override for {role} must be an object")
                assignment.update(patch)
                provider=assignment.get("provider")
                if provider not in available:
                    raise ValueError(f"Configured provider {provider!r} for {role} is not available/authenticated")
                if "model" not in patch:
                    assignment["model"]=self._model_for(provider,role,policy)
            result[role]=assignment

        # Cross-provider evaluator is preferred unless the operator explicitly overrode its provider.
        if "builder" in result and "evaluator" in result and len(available)>1 and "evaluator" not in overrides:
            if result["builder"]["provider"]==result["evaluator"]["provider"]:
                provider=next(x for x in available if x!=result["builder"]["provider"])
                result["evaluator"]={"provider":provider,"model":self._model_for(provider,"evaluator",policy)}
        return result

    @staticmethod
    def _model_for(provider: str, role: str, policy: str) -> str|None:
        if provider=="claude":
            if policy=="quality" and role in {"planner","architect","security_reviewer","final_reviewer"}:
                return "opus"
            return "sonnet"
        return None
