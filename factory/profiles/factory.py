from __future__ import annotations
from ..models import Phase
from ..domains import role_for
from ..taskgraph import TaskGraph
from .common import BaseRunner


class FactoryRunner(BaseRunner):
    profile="factory"

    @staticmethod
    def _evidence_ok(result) -> bool:
        evidence=result.get("evidence") or []
        if not evidence:
            return False
        explicit=[record.get("ok") for record in evidence if isinstance(record,dict) and "ok" in record]
        return not any(value is False for value in explicit)

    def _task_pipeline(self, run, task, ctx, domain):
        task_id=str(task["id"])
        hinted=str(task.get("profile","lite")).lower()
        max_passes=2 if hinted=="lite" else 3
        task_history=[]
        for attempt in range(1,max_passes+1):
            worker_role=role_for(domain,"worker")
            mode="build" if attempt==1 else "fix"
            worker=self.executor.execute(
                worker_role,
                {**task,"mode":mode,"attempt":attempt,"task_run_dir":str(run.run_dir/"artifacts"/"tasks"/task_id)},
                ctx,
            )
            self._ingest(run,worker)

            technical_ok=True
            if hinted=="pro":
                tester_role=role_for(domain,"tester")
                test=self.executor.execute(tester_role,{"mode":"task_test","task":task,"attempt":attempt},ctx)
                self._ingest(run,test)
                technical_ok=self._evidence_ok(test)

            evaluator_role="task_evaluator" if domain in {"code","operations"} else role_for(domain,"evaluator")
            evaluated=self.executor.execute(
                evaluator_role,
                {"mode":"task_evaluate","task":task,"attempt":attempt,"require_task_result":True},
                ctx,
            )
            self._ingest(run,evaluated)
            result=evaluated.get("task_result") or {
                "status":"UNVERIFIED",
                "findings":["task evaluator returned no task_result"],
            }
            result={**result,"task_id":task_id,"attempt":attempt,"profile":hinted,"technical_ok":technical_ok}
            if hinted=="pro" and not technical_ok and str(result.get("status","")).upper()=="PASS":
                result["status"]="FAIL"
                result.setdefault("findings",[]).append("technical tester produced no passing evidence")
            task_history.append(result)
            if str(result.get("status","")).upper()=="PASS":
                return {"ok":True,"history":task_history,"summary":worker.get("summary","")}
        return {"ok":False,"history":task_history,"summary":"task did not pass independent verification"}

    def run(self,request:str,guardian="guarded",domain="code",run_id=None):
        run=self._new(request,guardian,domain,run_id)
        state=self._state(run)
        ctx=self._context(run,guardian)

        if not (run.run_dir/"SPEC.md").exists():
            state.transition(Phase.PLANNING)
            self._ingest(run,self.executor.execute(role_for(domain,"planner"),{"request":request},ctx))
        if not (run.run_dir/"ARCHITECTURE.md").exists() or not (run.run_dir/"TASKS.json").exists():
            state.transition(Phase.ARCHITECTURE)
            self._ingest(run,self.executor.execute("architect",{"mode":"factory_architecture","require_task_graph":True,"domain":domain},ctx))

        tasks=self.store.read_json(run.run_dir,"TASKS.json",None)
        if not tasks:
            tasks={"tasks":[{
                "id":"T1",
                "title":"Implement requested system",
                "profile":"pro",
                "depends_on":[],
                "acceptance":["global rubric criteria relevant to this task pass"],
            }]}
            self.store.write_json(run.run_dir,"TASKS.json",tasks)

        graph=TaskGraph(tasks)
        task_outputs=[]
        for task in graph.order():
            state.transition(Phase.BUILDING,current_task=task["id"])
            result=self._task_pipeline(run,task,ctx,domain)
            task_outputs.append({"task":task,"result":result})
            self.store.write_json(run.run_dir,"TASK_OUTPUTS.json",task_outputs)
            if not result["ok"]:
                findings=self._findings(run)
                findings.append({
                    "id":f"TASK-{task['id']}",
                    "severity":"major",
                    "status":"open",
                    "rubric_id":None,
                    "detail":"Task failed independent task verification",
                })
                self.store.write_json(run.run_dir,"FINDINGS.json",findings)
                gate=self._gate(run,[{"name":"task_graph","ok":False}])
                state.transition(Phase.PAUSED,status="incomplete",blocked_task=task["id"])
                return self._write_report(run,gate,{"tasks_completed":len(task_outputs)-1,"blocked_task":task["id"]})

        state.transition(Phase.INTEGRATING)
        self._ingest(run,self.executor.execute("integrator",{"tasks":tasks,"outputs":task_outputs,"domain":domain},ctx))

        system_role="system_tester" if domain=="code" else role_for(domain,"tester")
        state.transition(Phase.TESTING)
        system_result=self.executor.execute(system_role,{"mode":"system_test","domain":domain},ctx)
        self._ingest(run,system_result)
        system_ok=self._evidence_ok(system_result)

        state.transition(Phase.EVALUATING)
        self._ingest(run,self.executor.execute(role_for(domain,"evaluator"),{"mode":"system_evaluate","domain":domain},ctx))

        state.transition(Phase.REVIEWING)
        sec=self.executor.execute("security_reviewer",{"mode":"security_review","domain":domain},ctx)
        self._ingest(run,sec)
        rev=self.executor.execute("final_reviewer",{"mode":"final_review","domain":domain},ctx)
        self._ingest(run,rev)

        mandatory=[
            {"name":"task_graph","ok":all(x["result"]["ok"] for x in task_outputs)},
            {"name":"system_test","ok":system_ok},
        ]
        if domain in {"code","operations"}:
            sec_evidence=[e for e in (sec.get("evidence") or []) if isinstance(e,dict) and (e.get("kind")=="security" or e.get("type")=="security")]
            mandatory.append({
                "name":"security",
                "ok":bool(sec_evidence) and not any(e.get("ok") is False for e in sec_evidence),
            })

        gate=self._gate(run,mandatory)
        state.transition(Phase.DONE if gate["done"] else Phase.PAUSED,status="done" if gate["done"] else "incomplete")
        return self._write_report(run,gate,{"tasks":len(graph.tasks),"task_outputs":task_outputs})
