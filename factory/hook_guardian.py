from __future__ import annotations
import json, os, sys
from .guardian import Guardian, Decision


def _decision(value: str, reason: str):
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":value,"permissionDecisionReason":reason}}))


def main() -> int:
    try:
        data=json.load(sys.stdin)
    except Exception:
        # Fail closed only for malformed hook input in locked mode; otherwise avoid breaking Claude.
        if os.environ.get("AAH_GUARDIAN_MODE","guarded")=="locked":
            print("AAH Guardian: malformed hook input",file=sys.stderr); return 2
        return 0
    mode=os.environ.get("AAH_GUARDIAN_MODE","guarded")
    root=os.environ.get("AAH_TARGET_ROOT") or data.get("cwd")
    g=Guardian(mode)
    name=str(data.get("tool_name") or "")
    inp=data.get("tool_input") or {}
    if name=="Bash":
        d=g.classify_command(str(inp.get("command") or ""))
        if d.decision==Decision.BLOCK:
            _decision("deny",d.reason); return 0
        if d.decision==Decision.REQUIRE_APPROVAL:
            _decision("ask",d.reason); return 0
        # WARN is advisory in non-locked modes; normal Claude permissions still apply.
        return 0
    if name in {"Write","Edit","NotebookEdit"}:
        path=str(inp.get("file_path") or inp.get("notebook_path") or "")
        if path and not g.can_write(path,root):
            _decision("deny",f"AAH Guardian protects writes to {path}"); return 0
    if name=="Read":
        path=str(inp.get("file_path") or "")
        if path and not g.can_read(path,root):
            _decision("deny",f"AAH Guardian protects sensitive reads from {path}"); return 0
    return 0

if __name__=="__main__": raise SystemExit(main())
