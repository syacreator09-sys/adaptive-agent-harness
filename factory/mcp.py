from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any


_CODEX_SECTION = re.compile(r'^\s*\[mcp_servers\.(?:"([^"]+)"|([A-Za-z0-9_.-]+))\]\s*$')
_MCP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class MCPDiscovery:
    """Discover configured MCP servers without persisting credentials.

    AAH never installs or invents third-party MCP servers. It discovers safe
    metadata, routes only explicitly requested servers, and leaves authentication
    under the provider/user configuration that already owns it.
    """

    def __init__(self, target: Path | str):
        self.target = Path(target).resolve()

    @staticmethod
    def _claude_server(name: str, raw: Any, source: str) -> dict[str, Any]:
        data = raw if isinstance(raw, dict) else {}
        transport = str(data.get("type") or "").lower()
        if not transport:
            if data.get("url"):
                transport = "http"
            elif data.get("command"):
                transport = "stdio"
            else:
                transport = "unknown"
        env = data.get("env") if isinstance(data.get("env"), dict) else {}
        headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
        return {
            "name": name,
            "provider": "claude",
            "source": source,
            "transport": transport,
            "env_names": sorted(str(key) for key in env),
            "header_names": sorted(str(key) for key in headers),
            "has_url": bool(data.get("url")),
            "has_command": bool(data.get("command")),
        }

    def _claude_project(self) -> list[dict[str, Any]]:
        path = self.target / ".mcp.json"
        if not path.is_file():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return [{
                "name": "<invalid-project-mcp-config>",
                "provider": "claude",
                "source": ".mcp.json",
                "transport": "invalid",
                "config_error": True,
            }]
        servers = value.get("mcpServers") if isinstance(value, dict) else None
        if not isinstance(servers, dict):
            return []
        return [self._claude_server(str(name), raw, ".mcp.json") for name, raw in servers.items()]

    @staticmethod
    def _codex_names(path: Path, source: str) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for line in lines:
            match = _CODEX_SECTION.match(line)
            if not match:
                continue
            name = match.group(1) or match.group(2)
            if name and name not in seen:
                seen.add(name)
                result.append({
                    "name": name,
                    "provider": "codex",
                    "source": source,
                    "transport": "provider-managed",
                })
        return result

    def inspect(self) -> dict[str, Any]:
        claude = self._claude_project()
        codex_project = self._codex_names(self.target / ".codex" / "config.toml", ".codex/config.toml")
        codex_user = self._codex_names(Path.home() / ".codex" / "config.toml", "~/.codex/config.toml")
        codex = codex_project + [
            item for item in codex_user
            if item["name"] not in {entry["name"] for entry in codex_project}
        ]

        by_name: dict[str, dict[str, Any]] = {}
        for item in claude + codex:
            if item.get("config_error"):
                continue
            name = str(item["name"])
            entry = by_name.setdefault(name, {"name": name, "providers": [], "sources": []})
            if item["provider"] not in entry["providers"]:
                entry["providers"].append(item["provider"])
            if item["source"] not in entry["sources"]:
                entry["sources"].append(item["source"])

        return {
            "claude": claude,
            "codex": codex,
            "servers": sorted(by_name.values(), key=lambda item: item["name"]),
            "project_mcp_config": str(self.target / ".mcp.json") if (self.target / ".mcp.json").is_file() else None,
            "persist_secret_values": False,
        }

    def resolve(
        self,
        provider: str,
        required: list[str] | tuple[str, ...] | None = None,
        optional: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        required_names = [str(name).strip() for name in (required or []) if str(name).strip()]
        optional_names = [str(name).strip() for name in (optional or []) if str(name).strip()]
        for name in required_names + optional_names:
            if not _MCP_NAME.fullmatch(name):
                raise ValueError(f"invalid MCP server name: {name!r}")

        info = self.inspect()
        provider_servers = {
            str(item["name"]): item
            for item in info.get(provider, [])
            if isinstance(item, dict) and not item.get("config_error") and item.get("name")
        }
        selected = [name for name in required_names + optional_names if name in provider_servers]
        missing_required = [name for name in required_names if name not in provider_servers]
        missing_optional = [name for name in optional_names if name not in provider_servers]
        unselected = sorted(name for name in provider_servers if name not in set(selected))
        return {
            "provider": provider,
            "required": required_names,
            "optional": optional_names,
            "selected": list(dict.fromkeys(selected)),
            "available": sorted(provider_servers),
            "unselected": unselected,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "project_mcp_config": info.get("project_mcp_config") if provider == "claude" else None,
            "persist_secret_values": False,
        }
