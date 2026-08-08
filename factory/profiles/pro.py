from __future__ import annotations
from ..models import Phase
from ..domains import role_for, gate_types
from ..progress import ProgressDetector
from ..config import AAHConfig
from .common import BaseRunner


class ProRunner(BaseRunner):
    profile="pro"

    @staticmethod
    def _evidence_gate(result, labels:set[str], name="domain_tests"):
        evidence=[record for record in (result.get("evidence") or []) if isinstance(record,dict) and str(record.get("type") or record.get("kind") or "") in labels]
        explicit=[record.get("ok") for record in evidence if "ok" in record]
        return {"name":name,"ok":bool(explicit) and all(value is True for value in explicit)}

    def run(self,request:str,guardian="guarded",domain="code",run_id=None,max_passes=None):
        if max_passes is None:
            max_passes=int(AAHConfig.load(self.target).data.get("execution",{}).get("max_pro_passes",5))
        max_passes=max(1,max_passes)
        run=self._new(request,guardian,domain,run_id); state=self._state(run); ctx=self._context(run,guardian); history=[]
        if not (run.run_dir/"SPEC.md").exists():
            state.transition(Phase.PLANNING); self._ingest(run,self.executor.execute(role_for(domain,"planner"),{"request":request},ctx))
        if not (run.run_dir/"ARCHITECTURE.md").exists():
            state.transition(Phase.ARCHITECTURE); self._ingest(run,self.executor.execute("architect",{"mode":"architecture"},ctx))
        state.transition(Phase.BUILDING); self._ingest(run,self.executor.execute(role_for(domain,"builder"),{"mode":"build"},ctx))
        detector=ProgressDetector(); labels=gate_types(domain,"pro_test")
        for i in range(1,max_passes+1):
            state.transition(Phase.TESTING,**{"pass":i})
            test_result=self.executor.execute(role_for(domain,"tester"),{"mode":"test","pass":i,"required_evidence_types":sorted(labels)},ctx); self._ingest(run,test_result)
            test_gate=self._evidence_gate(test_result,labels,name="domain_tests")
            state.transition(Phase.EVALUATING); self._ingest(run,self.executor.execute(role_for(domain,"evaluator"),{"mode":"evaluate","pass":i},ctx))
            rubric=self._rubric(run); findings=self._findings(run); gate=self._gate(run,[test_gate])
            passed,total=detector.score(rubric); history.append({"passed":passed,"total":total,"open_findings":sum(1 for f in findings if f.get("status","open")=="open")})
            if gate["done"]:
                state.transition(Phase.DONE,status="done"); return self._write_report(run,gate,{"passes":i})
            progress=detector.assess(history)
            if progress["stalled"] and i>=2:
                state.transition(Phase.ARCHITECTURE,reason="no_progress_rediagnosis"); self._ingest(run,self.executor.execute("architect",{"mode":"rediagnose","history":history},ctx))
            if i<max_passes:
                state.transition(Phase.FIXING); self._ingest(run,self.executor.execute(role_for(domain,"fixer"),{"mode":"fix","findings":findings,"pass":i},ctx))
        gate=self._gate(run,[test_gate]); state.transition(Phase.PAUSED,status="incomplete",escalation="factory")
        return self._write_report(run,gate,{"passes":max_passes,"escalation":"factory"})
