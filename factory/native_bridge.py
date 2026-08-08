from __future__ import annotations
from pathlib import Path
from .agents import AgentRegistry

NATIVE_ROLES=(
    "planner","architect","builder","tester","evaluator","fixer","worker",
    "task_evaluator","integrator","system_tester","security_reviewer","final_reviewer",
)

TOOL_MAP={
    "read":"Read",
    "glob":"Glob",
    "grep":"Grep",
    "edit":"Edit",
    "write":"Write",
    "shell":"Bash",
    "browser":"Skill",
}


def filename_for(role:str)->str:
    return f"aah-{role.replace('_','-')}.md"


def render_agent(role:str, registry:AgentRegistry|None=None)->str:
    registry=registry or AgentRegistry(); agent=registry.get(role); tools=[]
    for capability in agent.get("tools") or []:
        mapped=TOOL_MAP.get(capability)
        if mapped and mapped not in tools:
            tools.append(mapped)
    lines=[
        "---",
        f"name: aah-{role.replace('_','-')}",
        f"description: {agent['mission']}",
        "model: inherit",
    ]
    if tools:
        lines.append("tools: "+", ".join(tools))
    lines += [
        "---","",f"# {agent['identity']}","",agent["mission"],"","## Contract","",
        f"Inputs: {', '.join(agent['inputs'])}",
        f"Outputs: {', '.join(agent['outputs'])}","","## Rules","",
    ]
    lines += [f"- {rule}" for rule in agent["rules"]]
    lines += [
        "",
        "When the orchestrator supplies `run_dir`, coordination artifacts must be written only there. Product code changes are allowed only for roles whose mission explicitly requires implementation.",
        "",
    ]
    return "\n".join(lines)


def install_agents(target:Path|str, registry:AgentRegistry|None=None)->list[str]:
    target=Path(target); out=target/".claude"/"agents"; out.mkdir(parents=True,exist_ok=True); registry=registry or AgentRegistry(); written=[]
    for role in NATIVE_ROLES:
        path=out/filename_for(role); path.write_text(render_agent(role,registry),encoding="utf-8"); written.append(str(path))
    return written


def sync_repository(root:Path|str)->list[str]:
    return install_agents(Path(root))
