from __future__ import annotations
import json, os, shutil, subprocess, re
from pathlib import Path
from typing import Any
from .envs import EnvRouter
from .codex_profiles import has_profiles


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    name="base"
    def run(self, prompt: str, cwd: Path, model: str | None = None, tools: list[str] | None = None, guardian: str="guarded", access: str="workspace-write", env: dict[str,str] | None = None) -> dict[str,Any]:
        raise NotImplementedError


class ClaudeProvider(BaseProvider):
    name="claude"
    def __init__(self, subscription_only: bool=True):
        self.env_router=EnvRouter(subscription_only)

    def run(self,prompt,cwd,model=None,tools=None,guardian="guarded",access="workspace-write",env=None):
        cmd=["claude","-p",prompt,"--output-format","json","--no-session-persistence"]
        if model:
            cmd += ["--model",model]
        if tools:
            tool_list=",".join(tools)
            cmd += ["--tools",tool_list,"--allowedTools",*tools]
        cmd += ["--permission-mode","dontAsk"]
        cp=subprocess.run(cmd,cwd=str(cwd),env=env or self.env_router.sanitize_provider_env(),text=True,capture_output=True)
        if cp.returncode!=0:
            raise ProviderError(cp.stderr.strip() or f"claude exited {cp.returncode}")
        try:
            data=json.loads(cp.stdout)
            text=data.get("result","") if isinstance(data,dict) else cp.stdout
        except json.JSONDecodeError:
            text=cp.stdout
        return parse_agent_payload(text, provider="claude")


_NON_FATAL_CODEX_ITEM_ERROR=re.compile(r"in-process app-server event stream lagged; dropped \d+ events?",re.I)


class CodexProvider(BaseProvider):
    name="codex"
    def __init__(self, subscription_only: bool=True):
        self.env_router=EnvRouter(subscription_only)

    def run(self,prompt,cwd,model=None,tools=None,guardian="guarded",access="workspace-write",env=None):
        cmd=["codex","exec","--json","--sandbox",access]
        if has_profiles(cwd):
            profile="aah_readonly" if access=="read-only" else "aah_workspace"
            cmd += ["-c",f'default_permissions="{profile}"']
        if model:
            cmd += ["--model",model]
        cmd += [prompt]
        cp=subprocess.run(cmd,cwd=str(cwd),env=env or self.env_router.sanitize_provider_env(),text=True,capture_output=True)
        if cp.returncode!=0:
            raise ProviderError(cp.stderr.strip() or f"codex exited {cp.returncode}")

        events=[]
        for line in cp.stdout.splitlines():
            if not line.strip():
                continue
            try:
                event=json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event,dict):
                events.append(event)

        last_agent_text: str | None=None
        fatal_errors: list[str]=[]
        nonfatal_item_errors: list[str]=[]
        turn_completed=False

        for event in events:
            event_type=str(event.get("type") or "")
            if event_type=="item.completed":
                item=event.get("item") or {}
                if not isinstance(item,dict):
                    continue
                item_type=str(item.get("type") or "")
                if item_type=="agent_message" and isinstance(item.get("text"),str):
                    last_agent_text=item["text"]
                elif item_type=="error":
                    message=str(item.get("message") or item.get("error") or "codex item error")
                    if _NON_FATAL_CODEX_ITEM_ERROR.search(message):
                        nonfatal_item_errors.append(message)
                    else:
                        fatal_errors.append(message)
            elif event_type=="turn.completed":
                turn_completed=True
            elif event_type in {"turn.failed","error"}:
                detail=event.get("error") or event.get("message") or event
                fatal_errors.append(str(detail))

        # A completed turn with a final agent message wins over known non-fatal stream-lag items,
        # but real structured errors never silently become success.
        if fatal_errors:
            raise ProviderError("; ".join(dict.fromkeys(fatal_errors)))
        if events and not turn_completed and last_agent_text is None:
            raise ProviderError("codex JSON stream ended without turn.completed or agent_message")

        text=last_agent_text if last_agent_text is not None else cp.stdout
        result=parse_agent_payload(text, provider="codex")
        if nonfatal_item_errors:
            result.setdefault("provider_warnings",[]).extend(nonfatal_item_errors)
        return result


def parse_agent_payload(text: str, provider: str) -> dict[str,Any]:
    text=(text or "").strip()
    candidates=[text]
    if "```json" in text:
        candidates.append(text.split("```json",1)[1].split("```",1)[0])
    for candidate in candidates:
        try:
            value=json.loads(candidate)
            if isinstance(value,dict):
                value.setdefault("provider",provider)
                return value
        except Exception:
            pass
    return {"summary":text,"provider":provider,"artifacts":{},"evidence":[]}


class ProviderRegistry:
    @staticmethod
    def _version(exe: str) -> str | None:
        try:
            cp=subprocess.run([exe,"--version"],text=True,capture_output=True,timeout=4)
            out=(cp.stdout or cp.stderr).strip()
            return out.splitlines()[0] if out else None
        except Exception:
            return None

    @staticmethod
    def _claude_auth_status() -> dict[str,Any]:
        env=dict(os.environ)
        env.pop("ANTHROPIC_API_KEY",None)
        env.pop("ANTHROPIC_AUTH_TOKEN",None)
        try:
            cp=subprocess.run(["claude","auth","status"],text=True,capture_output=True,timeout=6,env=env)
        except Exception as exc:
            return {"authenticated":None,"auth":"status_probe_unavailable","auth_detail":type(exc).__name__}
        if cp.returncode==0:
            return {"authenticated":True,"auth":"subscription_or_cli_managed"}
        if cp.returncode==1:
            return {"authenticated":False,"auth":"not_logged_in"}
        return {"authenticated":None,"auth":"status_probe_unavailable"}

    @staticmethod
    def _codex_auth_status() -> dict[str,Any]:
        env=dict(os.environ)
        env.pop("OPENAI_API_KEY",None)
        try:
            cp=subprocess.run(["codex","login","status"],text=True,capture_output=True,timeout=6,env=env)
        except Exception as exc:
            return {"authenticated":None,"auth":"status_probe_unavailable","auth_detail":type(exc).__name__}
        if cp.returncode==0:
            return {"authenticated":True,"auth":"chatgpt_or_cli_managed"}
        combined=((cp.stdout or "")+"\n"+(cp.stderr or "")).lower()
        if any(x in combined for x in ["unknown", "unrecognized", "unexpected argument", "usage:"]):
            return {"authenticated":None,"auth":"status_probe_unavailable"}
        return {"authenticated":False,"auth":"not_logged_in"}

    @classmethod
    def discover(cls) -> dict[str,dict[str,Any]]:
        result={}
        for name in ["claude","codex"]:
            path=shutil.which(name)
            info={"available":bool(path),"path":path,"version":cls._version(name) if path else None}
            if not path:
                info.update({"authenticated":False,"auth":"unavailable"})
            elif name=="claude":
                info.update(cls._claude_auth_status())
            else:
                info.update(cls._codex_auth_status())
            result[name]=info
        return result

    @staticmethod
    def build(name: str, subscription_only: bool=True) -> BaseProvider:
        if name=="claude":
            return ClaudeProvider(subscription_only)
        if name=="codex":
            return CodexProvider(subscription_only)
        raise KeyError(name)
