from __future__ import annotations
from pathlib import Path
from typing import Any
from .router import AdaptiveRouter
from .profiles import LiteRunner, ProRunner, FactoryRunner
from .artifacts import ArtifactStore
class AutoOrchestrator:
    ORDER=["lite","pro","factory"]; RUNNERS={"lite":LiteRunner,"pro":ProRunner,"factory":FactoryRunner}
    def __init__(self,target:Path|str,executor_factory,router:AdaptiveRouter): self.target=Path(target).resolve(); self.executor_factory=executor_factory; self.router=router; self.store=ArtifactStore(self.target)
    def run(self,request:str,domain="code",profile="auto",guardian="auto")->dict[str,Any]:
        route=self.router.route(request); current=route["profile"] if profile=="auto" else profile; guard=route["guardian"] if guardian=="auto" else guardian; chain=[]; parent=None
        while True:
            ex=self.executor_factory(current,domain); result=self.RUNNERS[current](self.target,ex).run(request,guardian=guard,domain=domain); run_id=result["run_id"]; chain.append({"profile":current,"run_id":run_id,"done":result["done"]})
            if parent:
                run=self.store.get_run(run_id); self.store.write_json(run.run_dir,"PARENT_RUN.json",{"parent_run_id":parent})
            if result["done"] or profile!="auto": result["chain"]=chain; result["route"]=route; return result
            next_profile=(result.get("extra") or {}).get("escalation")
            if next_profile not in self.ORDER or self.ORDER.index(next_profile)<=self.ORDER.index(current): result["chain"]=chain; result["route"]=route; return result
            parent=run_id; current=next_profile
