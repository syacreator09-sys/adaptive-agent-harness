from __future__ import annotations
import json, os, sys
from .guardian import Guardian, Decision
from pathlib import Path

def _latest_guardian_mode(root: str | None) -> str:
    if not root: return "guarded"
    runs=Path(root)/".aah"/"runs"
    try:
        candidates=sorted([p for p in runs.iterdir() if p.is_dir()])
        if not candidates: return "guarded"
        state=candidates[-1]/"STATE.json"
        if state.exists():
            value=json.loads(state.read_text(encoding="utf-8")).get("guardian")
            if value in {"open","guarded","locked"}: return value
    except Exception:
        pass
    return "guarded"

def _decision(value: str, reason: str):
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":value,"permissionDecisionReason":reason}}))


def main() -> int:
    try:
        data=json.load(sys.stdin)
    except Exception:
        if os.environ.get("AAH_GUARDIAN_MODE","guarded")=="locked":
            print("AAH Guardian: malformed hook input",file=sys.stderr); return 2
        return 0
    root=os.environ.get("AAH_TARGET_ROOT") or data.get("cwd")
    mode=os.environ.get("AAH_GUARDIAN_MODE") or _latest_guardian_mode(root)
    g=Guardian(mode)
    role=data.get("agent_type") or os.environ.get("AAH_ROLE")
    name=str(data.get("tool_name") or "")
    inp=data.get("tool_input") or {}
    if name=="Bash":
        d=g.classify_command(str(inp.get("command") or ""),role=role)
        if d.decision==Decision.BLOCK:
            _decision("deny",d.reason); return 0
        if d.decision==Decision.REQUIRE_APPROVAL:
            _decision("ask",d.reason); return 0
        return 0
    if name in {"Write","Edit","NotebookEdit"}:
        path=str(inp.get("file_path") or inp.get("notebook_path") or "")
        if path and not g.can_write(path,root,role=role):
            _decision("deny",f"AAH Guardian protects writes to {path}"); return 0
    if name=="Read":
        path=str(inp.get("file_path") or "")
        if path and not g.can_read(path,root):
            _decision("deny",f"AAH Guardian protects sensitive reads from {path}"); return 0
    return 0

if __name__=="__main__": raise SystemExit(main())
