from __future__ import annotations
import os, shutil
from pathlib import Path
from typing import Any


class ToolRegistry:
    TOOLS = {
        "git":"git","docker":"docker","playwright":"playwright","node":"node","npm":"npm","pnpm":"pnpm","yarn":"yarn",
        "python":"python","pytest":"pytest","uv":"uv","poetry":"poetry","curl":"curl","ffmpeg":"ffmpeg","ffprobe":"ffprobe","semgrep":"semgrep",
        "rg":"rg","gh":"gh","supabase":"supabase","n8n":"n8n","bun":"bun","go":"go","cargo":"cargo",
    }
    GENERIC_NATIVE={"read","glob","grep","edit","write","shell"}
    PROVIDER_NATIVE={
        "claude":{
            "web":["WebSearch","WebFetch"],
            "files":["Read","Glob","Grep"],
        },
        # Codex filesystem is available through its sandbox, but live web search is configuration-dependent,
        # so AAH does not claim it unless an explicit web adapter is configured.
        "codex":{
            "files":[],
        },
    }
    CAPABILITIES = {
        "git":["git"], "http":["curl"], "browser":["playwright"], "docker":["docker"],
        "node":["node"], "python":["python"], "ffmpeg":["ffmpeg"], "media_probe":["ffprobe"],
        "security":["semgrep"], "github":["gh"], "supabase":["supabase"], "n8n":["n8n"],
    }
    ADAPTER_ENV={
        "image":"AAH_TOOL_IMAGE",
        "video":"AAH_TOOL_VIDEO",
        "voice":"AAH_TOOL_VOICE",
        "web":"AAH_TOOL_WEB",
    }

    @staticmethod
    def _resolve_adapter(value: str | None) -> str | None:
        if not value:
            return None
        expanded=os.path.expanduser(value)
        if os.path.sep in expanded or (os.path.altsep and os.path.altsep in expanded):
            path=Path(expanded)
            return str(path.resolve()) if path.exists() else None
        return shutil.which(expanded)

    @classmethod
    def discover(cls) -> dict[str,dict[str,Any]]:
        result={}
        for key, exe in cls.TOOLS.items():
            path=shutil.which(exe)
            result[key]={"available":bool(path),"path":path,"kind":"executable"}
        for cap,env_name in cls.ADAPTER_ENV.items():
            configured=os.environ.get(env_name)
            path=cls._resolve_adapter(configured)
            result[f"adapter:{cap}"]={
                "available":bool(path),
                "path":path,
                "kind":"adapter",
                "env":env_name,
                "configured":bool(configured),
            }
        return result

    @classmethod
    def resolve(cls, requested: list[str], discovered: dict[str,dict[str,Any]] | None = None, provider: str|None=None) -> dict[str,Any]:
        discovered=discovered or cls.discover()
        selected={}; missing=[]; native=[]; provider_tools=[]; notes=[]
        requested=list(dict.fromkeys(requested))
        has_shell="shell" in requested

        for cap in requested:
            if cap in cls.GENERIC_NATIVE:
                native.append(cap)
                continue

            provider_mapping=cls.PROVIDER_NATIVE.get(provider or "",{}).get(cap)
            if provider_mapping is not None:
                selected[cap]=f"provider:{provider}"
                provider_tools.extend(provider_mapping)
                continue

            adapter=discovered.get(f"adapter:{cap}",{})
            if adapter.get("available"):
                if has_shell:
                    selected[cap]=adapter.get("path")
                else:
                    missing.append(cap)
                    notes.append(f"{cap} adapter exists but role has no shell capability")
                continue

            candidates=cls.CAPABILITIES.get(cap,[cap])
            hit=next((c for c in candidates if discovered.get(c,{}).get("available")),None)
            if hit:
                if has_shell:
                    selected[cap]=discovered[hit].get("path") or hit
                else:
                    missing.append(cap)
                    notes.append(f"{cap} executable exists but role has no shell capability")
            else:
                missing.append(cap)

        return {
            "native":sorted(set(native)),
            "provider_tools":sorted(set(provider_tools)),
            "selected":selected,
            "missing":sorted(set(missing)),
            "notes":notes,
        }


class ToolRouter:
    def __init__(self, discovered: dict[str,dict[str,Any]]|None=None):
        self.discovered=discovered or ToolRegistry.discover()

    @staticmethod
    def infer_required(role: str, agent: dict[str,Any], task: dict[str,Any], context: dict[str,Any]|None=None) -> set[str]:
        required=set(agent.get("required_tools") or []) | set(task.get("required_tools") or [])
        request=str((context or {}).get("request") or task.get("request") or "").lower()
        if role=="content_producer":
            if any(word in request for word in ["image","imagen","carousel","carrusel","slide","poster","thumbnail","miniatura"]):
                required.add("image")
            if any(word in request for word in ["video","reel","short","tiktok","animate","animar"]):
                required.add("video")
            if any(word in request for word in ["voice","voiceover","voz","audio","narration","narración"]):
                required.add("voice")
        return required

    def for_agent(self, role: str, agent: dict[str,Any], task: dict[str,Any], provider: str, context: dict[str,Any]|None=None) -> dict[str,Any]:
        requested=list(dict.fromkeys((agent.get("tools") or [])+(task.get("tools") or [])))
        result=ToolRegistry.resolve(requested,self.discovered,provider=provider)
        result["required"]=sorted(self.infer_required(role,agent,task,context))
        return result
