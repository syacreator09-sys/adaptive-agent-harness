from __future__ import annotations
import argparse
from pathlib import Path
from .agents import AgentRegistry
from .model_router import ModelRouter


CORE_ROLES = [
    "planner", "architect", "builder", "tester", "evaluator", "fixer", "worker",
    "task_evaluator", "integrator", "system_tester", "security_reviewer", "final_reviewer",
]
_TOOL_MAP = {
    "read": "Read",
    "glob": "Glob",
    "grep": "Grep",
    "edit": "Edit",
    "write": "Write",
    "shell": "Bash",
    "browser": "Skill",
}


def render_agent(role: str, registry: AgentRegistry | None = None) -> str:
    registry = registry or AgentRegistry()
    agent = registry.get(role)
    tools: list[str] = []
    for tool in agent.get("tools", []):
        mapped = _TOOL_MAP.get(tool)
        if mapped and mapped not in tools:
            tools.append(mapped)
    plan = ModelRouter.resolve("claude", agent.get("capability") or "strong_coding", "balanced")
    lines = [
        "---",
        f"name: aah-{role.replace('_', '-')}",
        f"description: {agent['mission']}",
        # In native Claude Code mode, inherit is deliberately safer than pinning
        # a model that may not exist on every subscription. The body records the
        # recommended capability/model class for the orchestrator/user.
        "model: inherit",
    ]
    if tools:
        lines.append("tools: " + ", ".join(tools))
    lines += [
        "---", "", f"# {agent['identity']}", "", agent["mission"], "",
        "## Runtime identity", "",
        f"- Role: `{role}`",
        f"- Capability: `{agent.get('capability')}`",
        f"- Recommended Claude class: `{plan.recommended or 'inherit'}`",
        "- Fresh context: **required for every dispatch/pass**",
        "- Coordination: persistent AAH artifacts only; never another agent's hidden reasoning",
        "", "## Contract", "",
        f"Inputs: {', '.join(agent.get('inputs', []))}",
        f"Outputs: {', '.join(agent.get('outputs', []))}",
        "", "## Rules", "",
    ]
    lines += [f"- {rule}" for rule in agent.get("rules", [])]
    lines += [
        "",
        "When the orchestrator supplies `run_dir`, coordination artifacts must be written only there. "
        "Product code changes are allowed only for implementation roles whose mission explicitly requires them.",
        "Never claim completion; only AAH Final Gate may set DONE.",
    ]
    return "\n".join(lines) + "\n"


def render_all(output: Path | str, check: bool = False) -> list[str]:
    output = Path(output)
    registry = AgentRegistry()
    mismatches: list[str] = []
    if not check:
        output.mkdir(parents=True, exist_ok=True)
    for role in CORE_ROLES:
        path = output / f"aah-{role.replace('_', '-')}.md"
        expected = render_agent(role, registry)
        if check:
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != expected:
                mismatches.append(path.name)
        else:
            path.write_text(expected, encoding="utf-8")
    return mismatches


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render canonical AAH Claude agents")
    parser.add_argument("output")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    mismatches = render_all(args.output, check=args.check)
    if mismatches:
        print("AAH agent definitions out of sync: " + ", ".join(mismatches))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
