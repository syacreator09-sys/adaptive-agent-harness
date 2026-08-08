from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from .envs import EnvRouter
from .codex_profiles import has_profiles


class ProviderError(RuntimeError):
    pass


_MODEL_ERROR_HINTS = (
    "model not found",
    "unknown model",
    "invalid model",
    "unsupported model",
    "model is not available",
    "model unavailable",
    "does not have access to model",
    "don't have access to model",
    "not authorized to use model",
    "not available for your account",
    "not available on your plan",
)


def is_model_selection_error(exc: Exception | str) -> bool:
    text = str(exc).lower()
    return any(hint in text for hint in _MODEL_ERROR_HINTS)


def _provider_timeout() -> int:
    try:
        value = int(os.environ.get("AAH_PROVIDER_TIMEOUT_SECONDS", "1800"))
    except ValueError:
        value = 1800
    return max(30, min(value, 14400))


class BaseProvider:
    name = "base"

    def run(
        self,
        prompt: str,
        cwd: Path,
        model: str | None = None,
        tools: list[str] | None = None,
        guardian: str = "guarded",
        access: str = "workspace-write",
        env: dict[str, str] | None = None,
        effort: str | None = None,
        mcp: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class ClaudeProvider(BaseProvider):
    name = "claude"

    def __init__(self, subscription_only: bool = True):
        self.env_router = EnvRouter(subscription_only)

    def run(
        self,
        prompt,
        cwd,
        model=None,
        tools=None,
        guardian="guarded",
        access="workspace-write",
        env=None,
        effort=None,
        mcp=None,
    ):
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--no-session-persistence"]
        if model:
            cmd += ["--model", model]
        if effort in {"low", "medium", "high", "xhigh", "max"}:
            cmd += ["--effort", effort]

        # --tools controls built-in tools only. Pass an explicit empty string so
        # a role with no built-in tools cannot silently regain Claude defaults.
        builtin_tools = list(tools or [])
        cmd += ["--tools", ",".join(builtin_tools)]

        mcp = mcp or {}
        selected_mcp = [str(name) for name in mcp.get("selected", []) if name]
        allowed = list(builtin_tools)
        if selected_mcp:
            config = mcp.get("project_mcp_config")
            if not config:
                raise ProviderError("Claude MCP requested but project .mcp.json is unavailable")
            cmd += ["--strict-mcp-config", "--mcp-config", str(config)]
            allowed.extend(f"mcp__{name}__*" for name in selected_mcp)
            denied = [f"mcp__{name}__*" for name in mcp.get("unselected", []) if name]
            if denied:
                cmd += ["--disallowedTools", *denied]
        else:
            # Claude docs define strict MCP mode without --mcp-config as a way
            # to prevent project/user MCP servers from loading for this run.
            cmd += ["--strict-mcp-config"]

        if allowed:
            cmd += ["--allowedTools", *allowed]
        cmd += ["--permission-mode", "dontAsk"]
        try:
            cp = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=env or self.env_router.sanitize_provider_env(),
                text=True,
                capture_output=True,
                timeout=_provider_timeout(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"claude timed out after {_provider_timeout()} seconds") from exc
        if cp.returncode != 0:
            raise ProviderError(cp.stderr.strip() or cp.stdout.strip() or f"claude exited {cp.returncode}")
        try:
            data = json.loads(cp.stdout)
            text = data.get("result", "") if isinstance(data, dict) else cp.stdout
        except json.JSONDecodeError:
            text = cp.stdout
        result = parse_agent_payload(text, provider="claude")
        result.setdefault("provider_raw_model", model)
        return result


class CodexProvider(BaseProvider):
    name = "codex"

    def __init__(self, subscription_only: bool = True):
        self.env_router = EnvRouter(subscription_only)

    @staticmethod
    def _agent_text(stdout: str) -> str:
        text = stdout
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            if not line.strip().startswith("{"):
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except Exception:
                continue

        for event in events:
            event_type = str(event.get("type") or "").lower()
            if event_type in {"turn.failed", "error"}:
                detail = event.get("error") or event.get("message") or event
                raise ProviderError(str(detail))

        for event in reversed(events):
            item = event.get("item")
            if isinstance(item, dict):
                candidate = item.get("text") or item.get("message") or item.get("output")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate
            for key in ("result", "text", "message", "output"):
                candidate = event.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate
        return text

    def run(
        self,
        prompt,
        cwd,
        model=None,
        tools=None,
        guardian="guarded",
        access="workspace-write",
        env=None,
        effort=None,
        mcp=None,
    ):
        cmd = ["codex", "exec", "--json", "--sandbox", access]
        if has_profiles(cwd):
            profile = "aah_readonly" if access == "read-only" else "aah_workspace"
            cmd += ["-c", f'default_permissions="{profile}"']
        if model:
            cmd += ["--model", model]
        # Codex owns its MCP lifecycle through config.toml. AAH validates that
        # required server names exist and puts only selected names in the agent
        # context; it never rewrites user MCP credentials/config at runtime.
        cmd += [prompt]
        try:
            cp = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=env or self.env_router.sanitize_provider_env(),
                text=True,
                capture_output=True,
                timeout=_provider_timeout(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"codex timed out after {_provider_timeout()} seconds") from exc
        if cp.returncode != 0:
            raise ProviderError(cp.stderr.strip() or cp.stdout.strip() or f"codex exited {cp.returncode}")
        text = self._agent_text(cp.stdout)
        result = parse_agent_payload(text, provider="codex")
        result.setdefault("provider_raw_model", model)
        return result


def parse_agent_payload(text: str, provider: str) -> dict[str, Any]:
    # Real bug found live (2026-08-08, rebasing hardening/lite-pro-factory-v2
    # onto main): a real LITE planner produced a rich, correct SPEC.md whose
    # own text embeds ```python/```bash code fences. The old extraction
    # (`text.split("```json",1)[1].split("```",1)[0]`) takes the FIRST "```"
    # after the opening fence as the close -- for any agent response whose
    # JSON string VALUES contain their own triple-backtick fences (near
    # guaranteed for a real SPEC.md/PLANNING_REPORT.md with code examples),
    # this truncates mid-string, json.loads() raises, and the whole payload
    # silently degrades to {"artifacts": {}, "evidence": []} with the raw
    # text dumped as "summary" -- no crash, no obvious symptom, just every
    # real artifact discarded and (downstream) "Planner did not produce
    # SPEC.md" with no pointer back to this function. Reproduced directly:
    # parse_agent_payload of a fenced JSON payload whose artifacts.SPEC.md
    # value contains one embedded code block returns artifacts={}.
    #
    # Fixed by also trying the LAST "```" in the text as the closing
    # delimiter (rfind) -- correct whenever the model's reply is "prose,
    # then exactly one fenced JSON object, nothing after" (the documented
    # agent contract: "Return one JSON object"), which covers the real
    # failure above without weakening the existing first-close candidate
    # (tried first, so the common no-nested-fences case is unaffected).
    text = str(text or "").strip()
    candidates = [text]
    if "```json" in text:
        start = text.index("```json") + len("```json")
        first_close = text.find("```", start)
        if first_close != -1:
            candidates.append(text[start:first_close])
        last_close = text.rfind("```")
        if last_close != -1 and last_close != first_close and last_close > start:
            candidates.append(text[start:last_close])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                value.setdefault("provider", provider)
                value.setdefault("artifacts", {})
                value.setdefault("evidence", [])
                return value
        except Exception:
            pass
    return {"summary": text, "provider": provider, "artifacts": {}, "evidence": []}


class ProviderRegistry:
    @staticmethod
    def _version(exe: str) -> str | None:
        try:
            cp = subprocess.run([exe, "--version"], text=True, capture_output=True, timeout=4)
            out = (cp.stdout or cp.stderr).strip()
            return out.splitlines()[0] if out else None
        except Exception:
            return None

    @staticmethod
    def _claude_auth_status() -> dict[str, Any]:
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        try:
            cp = subprocess.run(["claude", "auth", "status"], text=True, capture_output=True, timeout=6, env=env)
        except Exception as exc:
            return {"authenticated": None, "auth": "status_probe_unavailable", "auth_detail": type(exc).__name__}
        if cp.returncode == 0:
            return {"authenticated": True, "auth": "subscription_or_cli_managed"}
        if cp.returncode == 1:
            return {"authenticated": False, "auth": "not_logged_in"}
        return {"authenticated": None, "auth": "status_probe_unavailable"}

    @staticmethod
    def _codex_auth_status() -> dict[str, Any]:
        env = dict(os.environ)
        env.pop("OPENAI_API_KEY", None)
        try:
            cp = subprocess.run(["codex", "login", "status"], text=True, capture_output=True, timeout=6, env=env)
        except Exception as exc:
            return {"authenticated": None, "auth": "status_probe_unavailable", "auth_detail": type(exc).__name__}
        if cp.returncode == 0:
            return {"authenticated": True, "auth": "chatgpt_or_cli_managed"}
        combined = ((cp.stdout or "") + "\n" + (cp.stderr or "")).lower()
        if any(token in combined for token in ["unknown", "unrecognized", "unexpected argument", "usage:"]):
            return {"authenticated": None, "auth": "status_probe_unavailable"}
        return {"authenticated": False, "auth": "not_logged_in"}

    @classmethod
    def discover(cls) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for name in ["claude", "codex"]:
            path = shutil.which(name)
            info: dict[str, Any] = {
                "available": bool(path),
                "path": path,
                "version": cls._version(name) if path else None,
            }
            if not path:
                info.update({"authenticated": False, "auth": "unavailable"})
            elif name == "claude":
                info.update(cls._claude_auth_status())
            else:
                info.update(cls._codex_auth_status())
            result[name] = info
        return result

    @staticmethod
    def build(name: str, subscription_only: bool = True) -> BaseProvider:
        if name == "claude":
            return ClaudeProvider(subscription_only)
        if name == "codex":
            return CodexProvider(subscription_only)
        raise KeyError(name)
