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
    """Deterministic policy layer shared by the runtime and Claude hook."""

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
    ARTIFACT_ONLY_ROLES={
        "planner","architect","tester","evaluator","task_evaluator","system_tester",
        "security_reviewer","final_reviewer","content_strategist","content_evaluator","fact_checker"
    }
    REVIEW_SAFE_COMMANDS=[re.compile(x,re.I) for x in [
        r"^pwd$", r"^ls(?:\s|$)", r"^git\s+(status|diff|log|show|rev-parse)(?:\s|$)",
        r"^(rg|grep|head|tail|wc)\s",
        r"^(python|python3)\s+-m\s+(pytest|unittest)(?:\s|$)", r"^pytest(?:\s|$)",
        r"^npm\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^pnpm\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^yarn\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^bun\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^cargo\s+(test|check|build)(?:\s|$)", r"^go\s+test(?:\s|$)",
        r"^(npx\s+)?playwright\s+test(?:\s|$)",
        r"^curl\s+[^;&|`]*https?://(127\.0\.0\.1|localhost)(:\d+)?(?:/[^\s]*)?(?:\s|$)",
    ]]

    def __init__(self, mode: str="guarded"): self.mode=mode if mode in {"open","guarded","locked"} else "guarded"

    @staticmethod
    def normalize_role(role: str | None) -> str | None:
        if not role: return None
        role=role.strip().lower().replace("-","_")
        if role.startswith("aah_"): role=role[4:]
        return role

    @staticmethod
    def _sensitive_command_text(command: str) -> bool:
        normalized=command.replace("\\","/").lower()
        return any(x in normalized for x in [".env", "/.ssh/", "/.aws/", "/.config/gcloud/", "/.azure/", "/.kube/config"])

    def _artifact_role_command(self, command: str, role: str) -> CommandDecision | None:
        compact=command.strip()
        if self._sensitive_command_text(compact):
            return CommandDecision(Decision.BLOCK,f"{role} cannot read sensitive paths from shell")
        # Chaining/subshells make a read-only allowlist ambiguous; reviewers issue one verification command per tool call.
        if any(tok in compact for tok in [";","&&","||","`","$(",">","<"]):
            return CommandDecision(Decision.BLOCK,f"{role} shell command is outside the verification allowlist")
        if any(p.search(compact) for p in self.REVIEW_SAFE_COMMANDS):
            return CommandDecision(Decision.ALLOW,"artifact-only verification command")
        return CommandDecision(Decision.BLOCK,f"{role} may only run bounded verification commands")

    def classify_command(self, command: str, role: str | None=None) -> CommandDecision:
        for p in self.UNIVERSAL_BLOCK:
            if p.search(command): return CommandDecision(Decision.BLOCK,"universal destructive action")
        normalized=self.normalize_role(role)
        if normalized in self.ARTIFACT_ONLY_ROLES:
            return self._artifact_role_command(command,normalized)
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
            try: p=str(Path(p).resolve().relative_to(Path(root).resolve())).replace("\\","/")
            except Exception: pass
        while p.startswith("./"): p=p[2:]
        return p

    @staticmethod
    def _env_path(clean: str) -> bool:
        name=Path(clean).name; return name==".env" or name.startswith(".env.")

    def can_read(self, path: str, root: str|None=None) -> bool:
        clean=self._clean(path,root); absolute=path.replace("\\","/")
        if self._env_path(clean): return False
        if any(x in absolute for x in self.SENSITIVE_HOME_PARTS): return False
        if clean.startswith(self.PROTECTED_READ_PREFIXES): return False
        return True

    def can_write(self, path: str, root: str|None=None, role: str|None=None) -> bool:
        clean=self._clean(path,root); absolute=path.replace("\\","/"); normalized=self.normalize_role(role)
        if normalized in self.ARTIFACT_ONLY_ROLES and not clean.startswith(".aah/runs/"): return False
        if self._env_path(clean): return False
        if any(x in absolute for x in self.SENSITIVE_HOME_PARTS): return False
        if clean.startswith(self.PROTECTED_WRITE_PREFIXES): return False
        if clean.startswith(".aah/") and not clean.startswith(".aah/runs/"): return False
        return True
