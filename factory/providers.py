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
    ) -> dict[str, Any]:
        raise NotImplementedError


class ClaudeProvider(BaseProvider):
    name = "claude"

    def __init__(self, subscription_only: bool = True):
        self.env_router = EnvRouter(subscription_only)

    def run(self, prompt, cwd, model=None, tools=None, guardian="guarded", access="workspace-write", env=None):
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--no-session-persistence"]
        if model:
            cmd += ["--model", model]
        if tools:
            tool_list = ",".join(tools)
            cmd += ["--tools", tool_list, "--allowedTools", *tools]
        cmd += ["--permission-mode", "dontAsk"]
        cp = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env or self.env_router.sanitize_provider_env(),
            text=True,
            capture_output=True,
        )
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

    def run(self, prompt, cwd, model=None, tools=None, guardian="guarded", access="workspace-write", env=None):
        cmd = ["codex", "exec", "--json", "--sandbox", access]
        if has_profiles(cwd):
            profile = "aah_readonly" if access == "read-only" else "aah_workspace"
            cmd += ["-c", f'default_permissions="{profile}"']
        if model:
            cmd += ["--model", model]
        cmd += [prompt]
        cp = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env or self.env_router.sanitize_provider_env(),
            text=True,
            capture_output=True,
        )
        if cp.returncode != 0:
            raise ProviderError(cp.stderr.strip() or cp.stdout.strip() or f"codex exited {cp.returncode}")
        text = self._agent_text(cp.stdout)
        result = parse_agent_payload(text, provider="codex")
        result.setdefault("provider_raw_model", model)
        return result


def parse_agent_payload(text: str, provider: str) -> dict[str, Any]:
    text = str(text or "").strip()
    candidates = [text]
    if "```json" in text:
        candidates.append(text.split("```json", 1)[1].split("```", 1)[0])
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
