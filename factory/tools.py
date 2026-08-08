from __future__ import annotations
import os
import shutil
from typing import Any


class ToolRegistry:
    TOOLS = {
        "git": "git", "docker": "docker", "playwright": "playwright", "node": "node",
        "npm": "npm", "pnpm": "pnpm", "yarn": "yarn", "python": "python",
        "pytest": "pytest", "uv": "uv", "poetry": "poetry", "curl": "curl",
        "ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "semgrep": "semgrep", "rg": "rg",
        "gh": "gh", "supabase": "supabase", "n8n": "n8n", "bun": "bun",
        "go": "go", "cargo": "cargo",
    }
    CORE_NATIVE = {"read", "glob", "grep", "edit", "write", "shell"}
    CAPABILITIES = {
        "git": ["git"], "http": ["curl"], "browser": ["playwright"], "docker": ["docker"],
        "node": ["node"], "python": ["python"], "ffmpeg": ["ffmpeg"],
        "media_probe": ["ffprobe", "ffmpeg"], "security": ["semgrep"], "github": ["gh"],
        "supabase": ["supabase"], "n8n": ["n8n"],
    }
    ADAPTER_ENV = {
        "web": "AAH_TOOL_WEB",
        "image": "AAH_TOOL_IMAGE",
        "video": "AAH_TOOL_VIDEO",
        "voice": "AAH_TOOL_VOICE",
    }

    @classmethod
    def discover(cls) -> dict[str, dict[str, Any]]:
        """Return safe capability metadata suitable for persistence."""
        result: dict[str, dict[str, Any]] = {}
        for key, exe in cls.TOOLS.items():
            path = shutil.which(exe)
            result[key] = {"available": bool(path), "path": path}
        for capability, env_name in cls.ADAPTER_ENV.items():
            result[f"adapter:{capability}"] = {
                "available": bool(os.environ.get(env_name)),
                "configured": bool(os.environ.get(env_name)),
                "env": env_name,
            }
        return result

    @classmethod
    def resolve(
        cls,
        requested: list[str],
        discovered: dict[str, dict[str, Any]] | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        discovered = discovered or cls.discover()
        selected: dict[str, str] = {}
        adapters: dict[str, str] = {}
        missing: list[str] = []
        native: list[str] = []
        provider_tools: list[str] = []

        def adapter_command(capability: str) -> str | None:
            env_name = cls.ADAPTER_ENV[capability]
            value = os.environ.get(env_name)
            return value if value else None

        for capability in requested:
            if capability in cls.CORE_NATIVE:
                native.append(capability)
                continue
            if capability == "files":
                native.append("read")
                continue
            if capability == "web":
                if provider == "claude":
                    native.append("web")
                    provider_tools.extend(["WebSearch", "WebFetch"])
                    continue
                command = adapter_command("web")
                if command:
                    adapters["web"] = command
                else:
                    missing.append("web")
                continue
            if capability in {"image", "video", "voice"}:
                command = adapter_command(capability)
                if command:
                    adapters[capability] = command
                else:
                    missing.append(capability)
                continue

            candidates = cls.CAPABILITIES.get(capability, [capability])
            hit = next(
                (candidate for candidate in candidates if discovered.get(candidate, {}).get("available")),
                None,
            )
            if hit:
                selected[capability] = hit
            else:
                missing.append(capability)

        return {
            "native": sorted(set(native)),
            "provider_tools": sorted(set(provider_tools)),
            "selected": selected,
            # Adapter command strings are runtime-only and must not be written to
            # project manifests, reports, or evidence.
            "adapters": adapters,
            "missing": sorted(set(missing)),
        }


class ToolRouter:
    def __init__(self, discovered: dict[str, dict[str, Any]] | None = None):
        self.discovered = discovered or ToolRegistry.discover()

    def for_agent(
        self,
        role: str,
        agent: dict[str, Any],
        task: dict[str, Any],
        provider: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del role, context
        requested = list(dict.fromkeys((agent.get("tools") or []) + (task.get("tools") or [])))
        return ToolRegistry.resolve(requested, self.discovered, provider=provider)
