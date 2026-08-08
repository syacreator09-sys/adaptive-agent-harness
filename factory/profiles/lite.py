from __future__ import annotations
from ..models import Phase
from ..domains import role_for
from ..config import AAHConfig
from .common import BaseRunner


class LiteRunner(BaseRunner):
    profile="lite"

    def run(self,request:str,guardian="open",domain="code",run_id=None,max_passes=None):
        if max_passes is None:
            max_passes=int(AAHConfig.load(self.target).data.get("execution",{}).get("max_lite_passes",3))
        max_passes=max(1,max_passes)
        run=self._new(request,guardian,domain,run_id)
        state=self._state(run)
        ctx=self._context(run,guardian)
        if not (run.run_dir/"SPEC.md").exists():
            state.transition(Phase.PLANNING)
            r=self.executor.execute(role_for(domain,"planner"),{"request":request,"mode":"plan"},ctx)
            self._ingest(run,r)
        state.transition(Phase.BUILDING)
        r=self.executor.execute(role_for(domain,"builder"),{"mode":"build","request":request},ctx)
        self._ingest(run,r)
        for i in range(1,max_passes+1):
            state.transition(Phase.EVALUATING,**{"pass":i})
            r=self.executor.execute(role_for(domain,"evaluator"),{"mode":"evaluate","pass":i},ctx)
            self._ingest(run,r)
            gate=self._gate(run)
            if gate["done"]:
                state.transition(Phase.DONE,status="done")
                return self._write_report(run,gate,{"passes":i})
            if i<max_passes:
                state.transition(Phase.FIXING)
                r=self.executor.execute(role_for(domain,"builder"),{"mode":"fix","pass":i,"findings":self._findings(run)},ctx)
                self._ingest(run,r)
        gate=self._gate(run)
        state.transition(Phase.PAUSED,status="incomplete",escalation="pro")
        return self._write_report(run,gate,{"passes":max_passes,"escalation":"pro"})
