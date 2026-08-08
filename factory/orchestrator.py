from __future__ import annotations
from pathlib import Path
from typing import Any
from .router import AdaptiveRouter
from .profiles import LiteRunner, ProRunner, FactoryRunner
from .artifacts import ArtifactStore
from .final_gate import normalize_rubric, normalize_findings


class AutoOrchestrator:
    ORDER=["lite","pro","factory"]
    RUNNERS={"lite":LiteRunner,"pro":ProRunner,"factory":FactoryRunner}

    def __init__(self,target:Path|str,executor_factory,router:AdaptiveRouter):
        self.target=Path(target).resolve()
        self.executor_factory=executor_factory
        self.router=router
        self.store=ArtifactStore(self.target)

    def _create_escalated_run(self, request:str, domain:str, profile:str, guardian:str, parent_run_id:str, parent_profile:str):
        child=self.store.create_run(request,profile,guardian,domain)
        parent=self.store.get_run(parent_run_id)
        context={
            "parent_run_id":parent_run_id,
            "parent_profile":parent_profile,
            "rubric":normalize_rubric(self.store.read_json(parent.run_dir,"RUBRIC.json",[])),
            "findings":normalize_findings(self.store.read_json(parent.run_dir,"FINDINGS.json",[])),
            "final_report":self.store.read_json(parent.run_dir,"FINAL_REPORT.json",{}),
        }
        self.store.write_json(child.run_dir,"PARENT_RUN.json",{"parent_run_id":parent_run_id,"parent_profile":parent_profile})
        self.store.write_json(child.run_dir,"ESCALATION_CONTEXT.json",context)
        return child

    def run(self,request:str,domain="code",profile="auto",guardian="auto") -> dict[str,Any]:
        route=self.router.route(request)
        current=route["profile"] if profile=="auto" else profile
        guard=route["guardian"] if guardian=="auto" else guardian
        chain=[]
        parent_run_id=None
        parent_profile=None

        while True:
            ex=self.executor_factory(current,domain)
            runner=self.RUNNERS[current](self.target,ex)
            if parent_run_id:
                child=self._create_escalated_run(request,domain,current,guard,parent_run_id,parent_profile or "unknown")
                result=runner.run(request,guardian=guard,domain=domain,run_id=child.run_id)
            else:
                result=runner.run(request,guardian=guard,domain=domain)

            run_id=result["run_id"]
            chain.append({"profile":current,"run_id":run_id,"done":result["done"]})
            if result["done"] or profile!="auto":
                result["chain"]=chain
                result["route"]=route
                return result

            next_profile=(result.get("extra") or {}).get("escalation")
            if next_profile not in self.ORDER or self.ORDER.index(next_profile)<=self.ORDER.index(current):
                result["chain"]=chain
                result["route"]=route
                return result

            parent_run_id=run_id
            parent_profile=current
            current=next_profile
