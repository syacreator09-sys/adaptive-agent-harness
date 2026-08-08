from __future__ import annotations
import json, os, sys
from pathlib import Path
from .guardian import Guardian, Decision


def _active_guardian_mode(root: str | None) -> str:
    """Native Claude sessions share a project hook. Use the strictest active run, never the newest by assumption."""
    if not root:
        return "guarded"
    runs=Path(root)/".aah"/"runs"
    rank={"open":0,"guarded":1,"locked":2}
    modes=[]
    try:
        for candidate in runs.iterdir():
            if not candidate.is_dir():
                continue
            state=candidate/"STATE.json"
            if not state.exists():
                continue
            data=json.loads(state.read_text(encoding="utf-8"))
            if data.get("status")=="done":
                continue
            mode=data.get("guardian")
            if mode in rank:
                modes.append(mode)
    except Exception:
        return "guarded"
    return max(modes,key=lambda m:rank[m]) if modes else "guarded"


def _decision(value: str, reason: str):
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":value,"permissionDecisionReason":reason}}))


def main() -> int:
    try:
        data=json.load(sys.stdin)
    except Exception:
        # Hook input that cannot be interpreted must not silently authorize a tool call.
        print("AAH Guardian: malformed PreToolUse input",file=sys.stderr)
        return 2

    root=os.environ.get("AAH_TARGET_ROOT") or data.get("cwd")
    mode=os.environ.get("AAH_GUARDIAN_MODE") or _active_guardian_mode(root)
    g=Guardian(mode)
    role=data.get("agent_type") or os.environ.get("AAH_ROLE")
    name=str(data.get("tool_name") or "")
    inp=data.get("tool_input") or {}

    if name=="Bash":
        decision=g.classify_command(str(inp.get("command") or ""),role=role)
        if decision.decision==Decision.BLOCK:
            _decision("deny",decision.reason); return 0
        if decision.decision==Decision.REQUIRE_APPROVAL:
            _decision("ask",decision.reason); return 0
        return 0

    if name in {"Write","Edit","NotebookEdit"}:
        path=str(inp.get("file_path") or inp.get("notebook_path") or "")
        if not path or not g.can_write(path,root,role=role):
            _decision("deny",f"AAH Guardian protects writes to {path or '[missing path]'}"); return 0
        return 0

    if name=="Read":
        path=str(inp.get("file_path") or "")
        if not path or not g.can_read(path,root):
            _decision("deny",f"AAH Guardian protects reads from {path or '[missing path]'}"); return 0
        return 0

    if name=="Grep":
        path=str(inp.get("path") or "")
        glob=str(inp.get("glob") or "")
        if ".env" in glob or any(x in glob for x in [".ssh",".aws",".kube"]):
            _decision("deny","AAH Guardian blocks Grep over sensitive file patterns"); return 0
        normalized=Guardian.normalize_role(role)
        if normalized in Guardian.ARTIFACT_ONLY_ROLES and not path:
            _decision("deny","AAH review roles must scope Grep to an explicit readable project path"); return 0
        if path and not g.can_read(path,root):
            _decision("deny",f"AAH Guardian protects Grep path {path}"); return 0
        return 0

    if name=="Glob":
        path=str(inp.get("path") or "")
        pattern=str(inp.get("pattern") or "")
        if any(x in pattern for x in [".env",".ssh",".aws",".kube"]):
            _decision("deny","AAH Guardian blocks Glob over sensitive file patterns"); return 0
        if path and not g.can_read(path,root):
            _decision("deny",f"AAH Guardian protects Glob path {path}"); return 0
        return 0

    return 0


if __name__=="__main__":
    raise SystemExit(main())
