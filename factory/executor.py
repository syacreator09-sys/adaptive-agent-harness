from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Any
from .agents import AgentRegistry
from .providers import ProviderRegistry, ProviderError, is_model_selection_error
from .tools import ToolRouter
from .envs import EnvRouter
from .mcp import MCPDiscovery


OUTPUT_CONTRACT = (
    "Return one JSON object with summary (string), artifacts (filename->text/JSON), "
    "and evidence (array). You may also return role-specific top-level machine-readable "
    "keys explicitly named in your Outputs contract. Never include secret values. "
    "Product source changes belong in the working tree, not in coordination artifacts."
)


class AgentExecutor:
    def __init__(
        self,
        target: Path,
        assignments: dict[str, dict[str, Any]],
        subscription_only: bool = True,
        registry: AgentRegistry | None = None,
        tool_router: ToolRouter | None = None,
    ):
        self.target = Path(target).resolve()
        self.assignments = assignments
        self.subscription_only = subscription_only
        self.registry = registry or AgentRegistry()
        self.tool_router = tool_router or ToolRouter()
        self.mcp = MCPDiscovery(self.target)
        self.calls: list[dict[str, Any]] = []

    def execute(
        self,
        role: str,
        task: dict[str, Any],
        context: dict[str, Any],
        session: str | None = None,
    ) -> dict[str, Any]:
        # A fresh UUID plus a fresh provider subprocess is created for every
        # dispatch. AAH never reuses evaluator context across passes.
        session = session or str(uuid.uuid4())
        agent = self.registry.get(role)
        assignment = dict(self.assignments.get(role, {}))
        provider_name = assignment.get("provider")
        if provider_name in {None, "none"}:
            raise RuntimeError(f"No provider available for {role}")

        resolution = self.tool_router.for_agent(
            role,
            agent,
            task,
            provider=provider_name,
            context=context,
        )
        required_tools = set(task.get("required_tools") or [])
        missing_required_tools = required_tools.intersection(resolution["missing"])
        if missing_required_tools:
            raise RuntimeError(f"Missing required tools for {role}: {sorted(missing_required_tools)}")

        mcp_resolution = self.mcp.resolve(
            provider_name,
            required=task.get("required_mcp") or [],
            optional=task.get("optional_mcp") or [],
        )
        if mcp_resolution["missing_required"]:
            raise RuntimeError(
                f"Missing required MCP servers for {role}/{provider_name}: "
                f"{mcp_resolution['missing_required']}"
            )

        enriched = dict(context)
        enriched["tool_resolution"] = resolution
        enriched["mcp_resolution"] = mcp_resolution
        enriched["agent_session"] = session
        enriched["agent_role"] = role
        provider = ProviderRegistry.build(provider_name, self.subscription_only)
        prompt = self._prompt(role, agent, task, enriched)
        tools = self._provider_tools(resolution, provider_name)
        access = "workspace-write" if any(item in resolution.get("native", []) for item in ["edit", "write"]) else "read-only"
        env = EnvRouter(self.subscription_only).scoped_provider_env(context.get("project", {}), role, task)
        env["AAH_GUARDIAN_MODE"] = str(context.get("guardian", "guarded"))
        env["AAH_TARGET_ROOT"] = str(self.target)
        env["AAH_ROLE"] = role
        env["AAH_SESSION_ID"] = session

        configured = assignment.get("model_candidates") or []
        if not configured and assignment.get("model"):
            configured = [assignment["model"]]
        candidates: list[str | None] = list(dict.fromkeys(configured))
        if assignment.get("model") and assignment["model"] not in candidates:
            candidates.insert(0, assignment["model"])
        # The user's current CLI default is the final compatibility fallback.
        candidates.append(None)

        last_error: Exception | None = None
        result: dict[str, Any] | None = None
        model_used: str | None = None
        for index, model in enumerate(candidates):
            try:
                result = provider.run(
                    prompt,
                    self.target,
                    model=model,
                    tools=tools,
                    guardian=context.get("guardian", "guarded"),
                    access=access,
                    env=env,
                    effort=assignment.get("effort"),
                    mcp=mcp_resolution,
                )
                model_used = model
                break
            except ProviderError as exc:
                last_error = exc
                has_next = index < len(candidates) - 1
                # Only model-selection/access failures are safe to replay with a
                # different model. Runtime/tool failures are never duplicated.
                if not has_next or not is_model_selection_error(exc):
                    raise

        if result is None:
            raise last_error or RuntimeError(f"Provider {provider_name} returned no result")

        call = {
            "role": role,
            "session": session,
            "provider": provider_name,
            "model": model_used,
            "capability": assignment.get("capability"),
            "effort": assignment.get("effort"),
            "task": task,
            "tools": resolution,
            "mcp": {
                "selected": mcp_resolution.get("selected", []),
                "missing_optional": mcp_resolution.get("missing_optional", []),
            },
        }
        self.calls.append(call)
        result.setdefault("session", session)
        result["_aah_role"] = role
        result["_aah_session"] = session
        result["_aah_assignment"] = {
            "provider": provider_name,
            "model": model_used,
            "capability": assignment.get("capability"),
            "effort": assignment.get("effort"),
            "mcp": list(mcp_resolution.get("selected", [])),
        }
        return result

    @staticmethod
    def _provider_tools(resolution: dict[str, Any], provider: str) -> list[str]:
        if provider != "claude":
            return []
        mapping = {
            "read": "Read",
            "glob": "Glob",
            "grep": "Grep",
            "edit": "Edit",
            "write": "Write",
            "shell": "Bash",
        }
        tools = {mapping[item] for item in resolution.get("native", []) if item in mapping}
        tools.update(str(item) for item in resolution.get("provider_tools", []) if item)
        return sorted(tools)

    @staticmethod
    def _prompt(role, agent, task, context):
        minimal = {key: value for key, value in context.items() if key != "secret_values"}
        rules = "\n- ".join(agent["rules"])
        return (
            f"You are the AAH {role}: {agent['identity']}.\n"
            f"Mission: {agent['mission']}\n"
            f"Inputs: {agent['inputs']}\n"
            f"Outputs: {agent['outputs']}\n"
            f"Rules:\n- {rules}\n\n"
            "This is a fresh independent invocation. Trust persistent artifacts and executable evidence, "
            "not conclusions from another agent. Use only MCP servers listed under mcp_resolution.selected.\n\n"
            f"Task:\n{json.dumps(task, indent=2, default=str)}\n\n"
            f"Context:\n{json.dumps(minimal, indent=2, default=str)}\n\n"
            f"{OUTPUT_CONTRACT}"
        )


class ScriptedExecutor:
    def __init__(self, scripts: dict[str, list[dict[str, Any]]]):
        self.scripts = {key: list(value) for key, value in scripts.items()}
        self.calls: list[dict[str, Any]] = []

    def execute(self, role, task, context, session=None):
        session = session or str(uuid.uuid4())
        self.calls.append({"role": role, "task": task, "session": session})
        queue = self.scripts.get(role, [])
        result = dict(queue.pop(0)) if queue else {"summary": f"scripted {role}"}
        result.setdefault("artifacts", {})
        result.setdefault("evidence", [])
        result.setdefault("session", session)
        result["_aah_role"] = role
        result["_aah_session"] = session
        result.setdefault(
            "_aah_assignment",
            {"provider": "scripted", "model": None, "capability": None, "effort": None, "mcp": []},
        )
        return result
