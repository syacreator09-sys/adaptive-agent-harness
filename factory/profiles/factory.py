from __future__ import annotations
from ..models import Phase
from ..domains import role_for, gate_types
from ..taskgraph import TaskGraph, TaskGraphError
from ..evidence import EvidenceStore, redact_data
from .common import BaseRunner


class FactoryRunner(BaseRunner):
    profile="factory"

    @staticmethod
    def _evidence_ok(result, labels:set[str], task_id:str|None=None) -> bool:
        evidence=[]
        for record in result.get("evidence") or []:
            if not isinstance(record,dict): continue
            label=str(record.get("type") or record.get("kind") or "")
            if label not in labels: continue
            if task_id is not None and str(record.get("task_id") or "")!=str(task_id): continue
            evidence.append(record)
        explicit=[record.get("ok") for record in evidence if "ok" in record]
        return bool(explicit) and all(value is True for value in explicit)

    def _task_pipeline(self, run, task, ctx, domain):
        task_id=str(task["id"]); hinted=str(task.get("profile","lite")).lower(); max_passes=2 if hinted=="lite" else 3; task_history=[]
        for attempt in range(1,max_passes+1):
            worker_role=role_for(domain,"worker"); mode="build" if attempt==1 else "fix"
            worker=self.executor.execute(worker_role,{**task,"mode":mode,"attempt":attempt,"task_run_dir":str(run.run_dir/"artifacts"/"tasks"/task_id)},ctx); self._ingest(run,worker)
            technical_ok=True
            if hinted=="pro":
                labels=gate_types(domain,"pro_test"); tester_role=role_for(domain,"tester")
                test=self.executor.execute(tester_role,{"mode":"task_test","task":task,"attempt":attempt,"required_evidence_types":sorted(labels)},ctx); self._ingest(run,test)
                technical_ok=self._evidence_ok(test,labels)
            evaluator_role="task_evaluator" if domain in {"code","operations"} else role_for(domain,"evaluator")
            evaluated=self.executor.execute(evaluator_role,{"mode":"task_evaluate","task":task,"attempt":attempt,"require_task_result":True,"required_evidence_types":["task_verification"]},ctx); self._ingest(run,evaluated)
            verification_ok=self._evidence_ok(evaluated,{"task_verification"},task_id)
            result=evaluated.get("task_result") or {"status":"UNVERIFIED","findings":["task evaluator returned no task_result"]}
            result={**result,"task_id":task_id,"attempt":attempt,"profile":hinted,"technical_ok":technical_ok,"verification_evidence_ok":verification_ok}
            if str(result.get("status","")).upper()=="PASS" and not verification_ok:
                result["status"]="UNVERIFIED"; result.setdefault("findings",[]).append("task evaluator supplied no explicit positive task_verification evidence")
            if hinted=="pro" and not technical_ok and str(result.get("status","")).upper()=="PASS":
                result["status"]="FAIL"; result.setdefault("findings",[]).append("task technical gate supplied no positive domain evidence")
            task_history.append(result)
            if str(result.get("status","")).upper()=="PASS": return {"ok":True,"history":task_history,"summary":worker.get("summary","")}
        return {"ok":False,"history":task_history,"summary":"task did not pass independent verification"}

    def _validated_graph(self, run, state, ctx, domain):
        schema={"tasks":"non-empty array","task_required_fields":["id","profile","depends_on","acceptance"],"profiles":["lite","pro"],"acceptance":"non-empty array of measurable criteria"}; last_error="missing TASKS.json"
        for attempt in range(1,3):
            tasks=self.store.read_json(run.run_dir,"TASKS.json",None)
            if tasks is not None:
                try: return TaskGraph(tasks)
                except TaskGraphError as exc: last_error=str(exc)
            state.transition(Phase.ARCHITECTURE,architecture_attempt=attempt,validation_error=last_error)
            self._ingest(run,self.executor.execute("architect",{"mode":"factory_architecture" if attempt==1 else "repair_task_graph","require_task_graph":True,"domain":domain,"task_graph_schema":schema,"validation_error":last_error},ctx))
        tasks=self.store.read_json(run.run_dir,"TASKS.json",None)
        try: return TaskGraph(tasks)
        except TaskGraphError as exc: last_error=str(exc)
        findings=self._findings(run); findings.append({"id":"F-TASK-GRAPH","severity":"major","status":"open","rubric_id":None,"detail":f"Architect failed to produce a valid task graph after repair attempt: {last_error}"}); self.store.write_json(run.run_dir,"FINDINGS.json",findings)
        EvidenceStore(run.run_dir).append({"id":"E-TASK-GRAPH-INVALID","type":"task_graph_validation","ok":False,"detail":last_error}); return None

    def run(self,request:str,guardian="guarded",domain="code",run_id=None):
        run=self._new(request,guardian,domain,run_id); state=self._state(run); ctx=self._context(run,guardian)
        if not (run.run_dir/"SPEC.md").exists():
            state.transition(Phase.PLANNING); self._ingest(run,self.executor.execute(role_for(domain,"planner"),{"request":request},ctx))
        if not (run.run_dir/"ARCHITECTURE.md").exists():
            state.transition(Phase.ARCHITECTURE); self._ingest(run,self.executor.execute("architect",{"mode":"factory_architecture","require_task_graph":True,"domain":domain,"task_graph_schema":{"required_fields":["id","profile","depends_on","acceptance"],"profiles":["lite","pro"]}},ctx))
        graph=self._validated_graph(run,state,ctx,domain)
        if graph is None:
            gate=self._gate(run,[{"name":"task_graph","ok":False}]); state.transition(Phase.PAUSED,status="incomplete",reason="invalid_task_graph"); return self._write_report(run,gate,{"tasks_completed":0,"blocked":"task_graph"})

        tasks={"tasks":graph.tasks}
        prior=self.store.read_json(run.run_dir,"TASK_OUTPUTS.json",[]) or []
        completed={str(item.get("task",{}).get("id")):item for item in prior if isinstance(item,dict) and item.get("result",{}).get("ok") is True}
        task_outputs=[]
        for task in graph.order():
            if task["id"] in completed:
                task_outputs.append(completed[task["id"]]); continue
            state.transition(Phase.BUILDING,current_task=task["id"])
            result=self._task_pipeline(run,task,ctx,domain); item={"task":task,"result":result}; task_outputs.append(item)
            self.store.write_json(run.run_dir,"TASK_OUTPUTS.json",redact_data(task_outputs))
            if not result["ok"]:
                findings=self._findings(run); findings.append({"id":f"TASK-{task['id']}","severity":"major","status":"open","rubric_id":None,"detail":"Task failed independent task verification"}); self.store.write_json(run.run_dir,"FINDINGS.json",findings)
                gate=self._gate(run,[{"name":"task_graph","ok":False}]); state.transition(Phase.PAUSED,status="incomplete",blocked_task=task["id"]); return self._write_report(run,gate,{"tasks_completed":len([x for x in task_outputs if x["result"]["ok"]]),"blocked_task":task["id"]})

        self.store.write_json(run.run_dir,"TASK_OUTPUTS.json",redact_data(task_outputs))
        state.transition(Phase.INTEGRATING); self._ingest(run,self.executor.execute("integrator",{"tasks":tasks,"outputs":task_outputs,"domain":domain},ctx))
        system_role="system_tester" if domain in {"code","operations"} else role_for(domain,"tester"); system_labels=gate_types(domain,"factory_system")
        state.transition(Phase.TESTING); system_result=self.executor.execute(system_role,{"mode":"system_test","domain":domain,"required_evidence_types":sorted(system_labels)},ctx); self._ingest(run,system_result); system_ok=self._evidence_ok(system_result,system_labels)
        state.transition(Phase.EVALUATING); self._ingest(run,self.executor.execute(role_for(domain,"evaluator"),{"mode":"system_evaluate","domain":domain},ctx))
        state.transition(Phase.REVIEWING); sec=self.executor.execute("security_reviewer",{"mode":"security_review","domain":domain},ctx); self._ingest(run,sec); rev=self.executor.execute("final_reviewer",{"mode":"final_review","domain":domain},ctx); self._ingest(run,rev)
        mandatory=[{"name":"task_graph","ok":all(x["result"]["ok"] for x in task_outputs)},{"name":"system_test","ok":system_ok}]
        if domain in {"code","operations"}:
            mandatory.append({"name":"security","ok":self._evidence_ok(sec,{"security"})})
        gate=self._gate(run,mandatory); state.transition(Phase.DONE if gate["done"] else Phase.PAUSED,status="done" if gate["done"] else "incomplete")
        return self._write_report(run,gate,{"tasks":len(graph.tasks),"task_outputs":task_outputs})
