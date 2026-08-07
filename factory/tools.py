from __future__ import annotations
import shutil
from typing import Any

class ToolRegistry:
    TOOLS={"git":"git","docker":"docker","playwright":"playwright","node":"node","npm":"npm","pnpm":"pnpm","yarn":"yarn","python":"python","pytest":"pytest","uv":"uv","poetry":"poetry","curl":"curl","ffmpeg":"ffmpeg","semgrep":"semgrep","rg":"rg","gh":"gh","supabase":"supabase","n8n":"n8n","bun":"bun","go":"go","cargo":"cargo"}
    NATIVE={"read","glob","grep","edit","write","shell","web","image","video","voice","files"}
    CAPABILITIES={"git":["git"],"http":["curl"],"browser":["playwright"],"docker":["docker"],"node":["node"],"python":["python"],"ffmpeg":["ffmpeg"],"security":["semgrep"],"github":["gh"],"supabase":["supabase"],"n8n":["n8n"]}
    @classmethod
    def discover(cls):
        return {key:{"available":bool(shutil.which(exe)),"path":shutil.which(exe)} for key,exe in cls.TOOLS.items()}
    @classmethod
    def resolve(cls,requested,discovered=None):
        discovered=discovered or cls.discover(); selected={}; missing=[]; native=[]
        for cap in requested:
            if cap in cls.NATIVE: native.append(cap); continue
            candidates=cls.CAPABILITIES.get(cap,[cap]); hit=next((c for c in candidates if discovered.get(c,{}).get("available")),None)
            if hit: selected[cap]=hit
            else: missing.append(cap)
        return {"native":sorted(native),"selected":selected,"missing":missing}
class ToolRouter:
    def __init__(self,discovered=None): self.discovered=discovered or ToolRegistry.discover()
    def for_agent(self,agent,task):
        requested=list(dict.fromkeys((agent.get("tools") or [])+(task.get("tools") or []))); return ToolRegistry.resolve(requested,self.discovered)
