from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

class Decision(str, Enum):
    ALLOW="allow"; WARN="warn"; REQUIRE_APPROVAL="require_approval"; BLOCK="block"

@dataclass
class CommandDecision:
    decision: Decision
    reason: str

class Guardian:
    """Small deterministic policy layer shared by the runtime and Claude hook."""

    UNIVERSAL_BLOCK=[
        re.compile(r"(^|\s)rm\s+-rf\s+/($|\s)"),
        re.compile(r"git\s+push\s+.*--force.*\b(main|master)\b"),
        re.compile(r"git\s+reset\s+--hard\s+origin/(main|master)"),
        re.compile(r"\bmkfs(?:\.|\s)"),
        re.compile(r"\bdd\s+if=.*\bof=/dev/"),
        re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"),
    ]
    PROD_PATTERNS=[re.compile(x,re.I) for x in [
        r"kubectl\s+(apply|delete|replace|patch)", r"terraform\s+(apply|destroy)",
        r"\bDROP\s+DATABASE\b", r"\bDROP\s+TABLE\b", r"\bTRUNCATE\s+TABLE\b",
        r"\bproduction\b", r"\bprod\b", r"git\s+push\b",
    ]]
    PROTECTED_WRITE_PREFIXES=(".git/", ".claude/", ".codex/", ".aah/runtime/", ".aah/bin/")
    PROTECTED_READ_PREFIXES=(".git/", ".aah/runtime/", ".aah/bin/")
    SENSITIVE_HOME_PARTS=("/.ssh/", "/.aws/", "/.config/gcloud/", "/.azure/", "/.kube/config")

    def __init__(self, mode: str="guarded"): self.mode=mode if mode in {"open","guarded","locked"} else "guarded"

    def classify_command(self, command: str) -> CommandDecision:
        for p in self.UNIVERSAL_BLOCK:
            if p.search(command): return CommandDecision(Decision.BLOCK,"universal destructive action")
        if re.search(r"\b(curl|wget)\b[^|]*\|\s*(bash|sh)\b",command):
            if self.mode=="locked": return CommandDecision(Decision.BLOCK,"remote pipe-to-shell blocked in LOCKED")
            if self.mode=="guarded": return CommandDecision(Decision.REQUIRE_APPROVAL,"remote pipe-to-shell requires approval")
            return CommandDecision(Decision.WARN,"remote pipe-to-shell is risky")
        if any(p.search(command) for p in self.PROD_PATTERNS):
            if self.mode=="locked": return CommandDecision(Decision.REQUIRE_APPROVAL,"production-sensitive action")
            if self.mode=="guarded": return CommandDecision(Decision.WARN,"production-sensitive action")
        return CommandDecision(Decision.ALLOW,"routine command")

    @staticmethod
    def _clean(path: str, root: str | None=None) -> str:
        p=path.replace("\\","/")
        if root:
            try:
                p=str(Path(p).resolve().relative_to(Path(root).resolve())).replace("\\","/")
            except Exception:
                pass
        while p.startswith("./"): p=p[2:]
        return p

    @staticmethod
    def _env_path(clean: str) -> bool:
        name=Path(clean).name
        return name==".env" or name.startswith(".env.")

    def can_read(self, path: str, root: str|None=None) -> bool:
        clean=self._clean(path,root); absolute=path.replace("\\","/")
        if self._env_path(clean): return False
        if any(x in absolute for x in self.SENSITIVE_HOME_PARTS): return False
        if clean.startswith(self.PROTECTED_READ_PREFIXES): return False
        return True

    def can_write(self, path: str, root: str|None=None) -> bool:
        clean=self._clean(path,root); absolute=path.replace("\\","/")
        if self._env_path(clean): return False
        if any(x in absolute for x in self.SENSITIVE_HOME_PARTS): return False
        if clean.startswith(self.PROTECTED_WRITE_PREFIXES): return False
        if clean.startswith(".aah/") and not clean.startswith(".aah/runs/"): return False
        return True
