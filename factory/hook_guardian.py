from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from .guardian import Guardian, Decision


def _active_guardian_mode(root: str | None) -> str:
    if not root:
        return "guarded"
    runs = Path(root) / ".aah" / "runs"
    rank = {"open": 0, "guarded": 1, "locked": 2}
    modes: list[str] = []
    try:
        for candidate in runs.iterdir():
            if not candidate.is_dir():
                continue
            state = candidate / "STATE.json"
            if not state.exists():
                continue
            data = json.loads(state.read_text(encoding="utf-8"))
            if data.get("status") in {"done", "failed", "incomplete", "paused"}:
                continue
            mode = data.get("guardian")
            if mode in rank:
                modes.append(mode)
    except Exception:
        return "guarded"
    return max(modes, key=lambda item: rank[item]) if modes else "guarded"


def _decision(value: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": value,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("AAH Guardian: malformed PreToolUse input", file=sys.stderr)
        return 2

    root = os.environ.get("AAH_TARGET_ROOT") or data.get("cwd")
    mode = os.environ.get("AAH_GUARDIAN_MODE") or _active_guardian_mode(root)
    guardian = Guardian(mode)
    role = data.get("agent_type") or os.environ.get("AAH_ROLE")
    tool_name = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input") or {}

    if tool_name == "Bash":
        result = guardian.classify_command(str(tool_input.get("command") or ""), role=role)
        if result.decision == Decision.BLOCK:
            _decision("deny", result.reason)
            return 0
        if result.decision == Decision.REQUIRE_APPROVAL:
            _decision("ask", result.reason)
            return 0
        return 0

    if tool_name in {"Write", "Edit", "NotebookEdit"}:
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        if not path or not guardian.can_write(path, root, role=role):
            _decision("deny", f"AAH Guardian protects writes to {path or '[missing path]'}")
        return 0

    if tool_name == "Read":
        path = str(tool_input.get("file_path") or "")
        if not path or not guardian.can_read(path, root):
            _decision("deny", f"AAH Guardian protects reads from {path or '[missing path]'}")
        return 0

    if tool_name == "Grep":
        path = str(tool_input.get("path") or "")
        glob = str(tool_input.get("glob") or "")
        if any(token in glob.lower() for token in [".env", ".ssh", ".aws", ".kube", "credential"]):
            _decision("deny", "AAH Guardian blocks Grep over sensitive patterns")
            return 0
        normalized = Guardian.normalize_role(role)
        if normalized in Guardian.ARTIFACT_ONLY_ROLES and not path:
            _decision("deny", "AAH review roles must scope Grep to an explicit project path")
            return 0
        if path and not guardian.can_read(path, root):
            _decision("deny", f"AAH Guardian protects Grep path {path}")
        return 0

    if tool_name == "Glob":
        path = str(tool_input.get("path") or root or "")
        pattern = str(tool_input.get("pattern") or "")
        if any(token in pattern.lower() for token in [".env", ".ssh", ".aws", ".kube", "credential"]):
            _decision("deny", "AAH Guardian blocks Glob over sensitive patterns")
            return 0
        if not path or not guardian.can_read(path, root):
            _decision("deny", f"AAH Guardian protects Glob path {path or '[missing path]'}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
