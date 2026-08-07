from __future__ import annotations
import json, uuid
from pathlib import Path
from typing import Any
from .agents import AgentRegistry
from .providers import ProviderRegistry
from .tools import ToolRouter
from .envs import EnvRouter

OUTPUT_CONTRACT = "Return one JSON object with summary (string), artifacts (filename->text/JSON), and evidence (array). You may also return role-specific top-level machine-readable keys explicitly named in your Outputs contract (for example task_result). Never include secret values. Product source changes belong in the working tree, not in artifacts."

class AgentExecutor:
    def __init__(self,target:Path,assignments:dict[str,dict[str,Any]],subscription_only:bool=True,registry:AgentRegistry|None=None,tool_router:ToolRouter|None=None):
        self.target=Path(target); self.assignments=assignments; self.subscription_only=subscription_only
        self.registry=registry or AgentRegistry(); self.tool_router=tool_router or ToolRouter(); self.calls=[]
    def execute(self,role:str,task:dict[str,Any],context:dict[str,Any],session:str|None=None)->dict[str,Any]:
        session=session or str(uuid.uuid4()); agent=self.registry.get(role); assignment=self.assignments.get(role,{})
        provider_name=assignment.get("provider")
        if provider_name in {None,"none"}: raise RuntimeError(f"No provider available for {role}")
        resolution=self.tool_router.for_agent(agent,task)
        required=set(task.get("required_tools") or [])
        missing_required=required.intersection(resolution["missing"])
        if missing_required: raise RuntimeError(f"Missing required tools for {role}: {sorted(missing_required)}")
        enriched=dict(context); enriched["tool_resolution"]=resolution
        provider=ProviderRegistry.build(provider_name,self.subscription_only)
        prompt=self._prompt(role,agent,task,enriched)
        tools=self._provider_tools(resolution.get("native",[]),provider_name)
        access="workspace-write" if any(x in resolution.get("native",[]) for x in ["edit","write"]) else "read-only"
        env=EnvRouter(self.subscription_only).scoped_provider_env(context.get("project",{}),role,task)
        env["AAH_GUARDIAN_MODE"]=str(context.get("guardian","guarded"))
        env["AAH_TARGET_ROOT"]=str(self.target)
        env["AAH_ROLE"]=role
        result=provider.run(prompt,self.target,model=assignment.get("model"),tools=tools,guardian=context.get("guardian","guarded"),access=access,env=env)
        self.calls.append({"role":role,"session":session,"provider":provider_name,"task":task,"tools":resolution}); result.setdefault("session",session); return result
    @staticmethod
    def _provider_tools(tools:list[str],provider:str)->list[str]:
        if provider!="claude": return []
        mapping={"read":"Read","glob":"Glob","grep":"Grep","edit":"Edit","write":"Write","shell":"Bash"}
        return sorted({mapping[t] for t in tools if t in mapping})
    @staticmethod
    def _prompt(role,agent,task,context):
        minimal={k:v for k,v in context.items() if k!="secret_values"}; rules="\n- ".join(agent["rules"])
        return (f"You are the AAH {role}: {agent['identity']}.\nMission: {agent['mission']}\n"
                f"Inputs: {agent['inputs']}\nOutputs: {agent['outputs']}\nRules:\n- {rules}\n\n"
                f"Task:\n{json.dumps(task,indent=2,default=str)}\n\nContext:\n{json.dumps(minimal,indent=2,default=str)}\n\n{OUTPUT_CONTRACT}")

class ScriptedExecutor:
    def __init__(self,scripts:dict[str,list[dict[str,Any]]]): self.scripts={k:list(v) for k,v in scripts.items()}; self.calls=[]
    def execute(self,role,task,context,session=None):
        session=session or str(uuid.uuid4()); self.calls.append({"role":role,"task":task,"session":session})
        queue=self.scripts.get(role,[]); result=dict(queue.pop(0)) if queue else {"summary":f"scripted {role}"}
        result.setdefault("artifacts",{}); result.setdefault("evidence",[]); result.setdefault("session",session); return result
