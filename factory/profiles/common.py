from __future__ import annotations
import json, subprocess
from pathlib import Path
from typing import Any
from ..artifacts import ArtifactStore
from ..evidence import EvidenceStore
from ..state import RunStateStore
from ..models import Phase
from ..final_gate import FinalGate
from ..project_adapter import ProjectAdapter
from ..gitops import GitCheckpoints

class BaseRunner:
    profile="base"
    def __init__(self,target:Path|str,executor): self.target=Path(target).resolve(); self.executor=executor; self.store=ArtifactStore(self.target)
    def _new(self,request,guardian,domain="code",run_id=None):
        if run_id: return self.store.get_run(run_id)
        run=self.store.create_run(request,self.profile,guardian,domain)
        snap=GitCheckpoints(self.target).snapshot()
        state=self._state(run).load(); state["git_base"]=snap.get("head"); state["git_base_dirty"]=snap.get("dirty",False); self._state(run).save(state)
        req=self.store.read_json(run.run_dir,"REQUEST.json",{}); req["git_base"]=snap.get("head"); self.store.write_json(run.run_dir,"REQUEST.json",req)
        return run
    def _context(self,run,guardian):
        return {"run_id":run.run_id,"run_dir":str(run.run_dir),"guardian":guardian,"project":ProjectAdapter(self.target).inspect(),"artifact_protocol":"Use files under run_dir only for AAH coordination. Never write secrets."}
    def _ingest(self,run,result):
        for name,value in (result.get("artifacts") or {}).items():
            if name in {"STATE.json","REQUEST.json","EVIDENCE.jsonl"}: continue
            if isinstance(value,(dict,list)): self.store.write_json(run.run_dir,name,value)
            else: self.store.write_text(run.run_dir,name,str(value))
        ev=EvidenceStore(run.run_dir)
        for rec in result.get("evidence") or []: ev.append(rec)
    def _rubric(self,run): return self.store.read_json(run.run_dir,"RUBRIC.json",[]) or []
    def _findings(self,run): return self.store.read_json(run.run_dir,"FINDINGS.json",[]) or []
    def _gate(self,run,mandatory=None):
        return FinalGate(run.run_dir).evaluate(self._rubric(run),self._findings(run),mandatory)
    def _state(self,run): return RunStateStore(run.run_dir)
    def _write_report(self,run,gate,extra=None):
        state=self._state(run).load(); state["git_current"]=GitCheckpoints(self.target).snapshot().get("head"); self._state(run).save(state); report={"run_id":run.run_id,"profile":self.profile,"done":gate["done"],"gate":gate,"state":state,"extra":extra or {}}
        self.store.write_json(run.run_dir,"FINAL_REPORT.json",report)
        lines=[f"# AAH Final Report — {run.run_id}","",f"Profile: **{self.profile.upper()}**",f"Done: **{gate['done']}**",f"Rubric: {gate['passed']}/{gate['required']}"]
        if gate["failures"]: lines += ["","## Blocking items"]+[f"- {x}" for x in gate["failures"]]
        self.store.write_text(run.run_dir,"FINAL_REPORT.md","\n".join(lines))
        return report
