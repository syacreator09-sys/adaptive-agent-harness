from __future__ import annotations
import posixpath
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Decision(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


@dataclass
class CommandDecision:
    decision: Decision
    reason: str


class Guardian:
    """Deterministic policy layer shared by runtime and Claude PreToolUse hook."""

    UNIVERSAL_BLOCK = [
        re.compile(r"(^|\s)rm\s+-rf\s+/($|\s)"),
        re.compile(r"git\s+push\s+.*--force.*\b(main|master)\b"),
        re.compile(r"git\s+reset\s+--hard\s+origin/(main|master)"),
        re.compile(r"\bmkfs(?:\.|\s)"),
        re.compile(r"\bdd\s+if=.*\bof=/dev/"),
        re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"),
    ]
    PROD_PATTERNS = [re.compile(pattern, re.I) for pattern in [
        r"kubectl\s+(apply|delete|replace|patch)", r"terraform\s+(apply|destroy)",
        r"\bDROP\s+DATABASE\b", r"\bDROP\s+TABLE\b", r"\bTRUNCATE\s+TABLE\b",
        r"\bproduction\b", r"\bprod\b", r"git\s+push\b",
    ]]
    PROTECTED_WRITE_PREFIXES = (".git/", ".claude/", ".codex/", ".aah/runtime/", ".aah/bin/")
    PROTECTED_READ_PREFIXES = (".git/", ".aah/runtime/", ".aah/bin/")
    SENSITIVE_HOME_PARTS = ("/.ssh/", "/.aws/", "/.config/gcloud/", "/.azure/", "/.kube/config")

    ARTIFACT_ONLY_ROLES = {
        "planner", "architect", "tester", "evaluator", "task_evaluator", "system_tester",
        "security_reviewer", "final_reviewer", "content_strategist", "content_evaluator", "fact_checker",
    }
    EVIDENCE_WRITER_ROLES = {
        "tester", "evaluator", "task_evaluator", "system_tester",
        "security_reviewer", "content_evaluator", "fact_checker",
    }
    # These role scopes apply only to native run coordination files. Product
    # filesystem permissions remain governed separately.
    TASK_ONLY_RUN_ROLES = {"worker", "task_evaluator"}
    ROOT_ONLY_RUN_ROLES = {
        "planner", "content_strategist", "architect", "builder", "fixer", "integrator",
        "evaluator", "system_tester", "security_reviewer", "final_reviewer",
    }
    ROLE_RUN_WRITES: dict[str, set[str]] = {
        "planner": {"SPEC.md", "RUBRIC.json", "PLANNING_REPORT.md"},
        "content_strategist": {"SPEC.md", "RUBRIC.json", "PLANNING_REPORT.md"},
        "architect": {"ARCHITECTURE.md", "TASKS.json", "ARCHITECTURE_REPORT.md"},
        "builder": {"BUILD_REPORT.md", "FIX_REPORT.md"},
        "fixer": {"FIX_REPORT.md"},
        "worker": {"BUILD_REPORT.md", "FIX_REPORT.md", "TASK_BUILD_REPORT.md", "TASK_FIX_REPORT.md"},
        "integrator": {"INTEGRATION_REPORT.md"},
        "content_producer": {"BUILD_REPORT.md", "FIX_REPORT.md"},
        "researcher": {"BUILD_REPORT.md", "FIX_REPORT.md"},
        "tester": {"TEST_REPORT.md", "EVIDENCE_DRAFT.json"},
        "evaluator": {"RUBRIC_STATUS.json", "FINDINGS.json", "FINDINGS.md", "EVALUATION_REPORT.md", "EVIDENCE_DRAFT.json"},
        "content_evaluator": {"RUBRIC_STATUS.json", "FINDINGS.json", "FINDINGS.md", "EVALUATION_REPORT.md", "SYSTEM_TEST_REPORT.md", "EVIDENCE_DRAFT.json"},
        "fact_checker": {"RUBRIC_STATUS.json", "FINDINGS.json", "FINDINGS.md", "EVALUATION_REPORT.md", "SYSTEM_TEST_REPORT.md", "EVIDENCE_DRAFT.json"},
        "system_tester": {"SYSTEM_TEST_REPORT.md", "EVIDENCE_DRAFT.json"},
        "security_reviewer": {"SECURITY_REPORT.md", "EVIDENCE_DRAFT.json"},
        "final_reviewer": {"REVIEW_REPORT.md"},
        "task_evaluator": {
            "RUBRIC_STATUS.json", "FINDINGS.json", "FINDINGS.md", "EVALUATION_REPORT.md",
            "TASK_RUBRIC_STATUS.json", "TASK_FINDINGS.json", "TASK_FINDINGS.md", "TASK_EVALUATION_REPORT.md",
            "EVIDENCE_DRAFT.json",
        },
    }
    RUNTIME_OWNED_BASENAMES = {
        "STATE.json", "REQUEST.json", "EVENTS.jsonl", "AGENTS.jsonl", "EVIDENCE.jsonl",
        "CONTRACT.json", "RUBRIC_BASELINE.json", "FINAL_REPORT.json", "FINAL_REPORT.md",
        "PARENT_RUN.json", "ESCALATION_CONTEXT.json", "TASK_OUTPUTS.json",
    }

    REVIEW_SAFE_COMMANDS = [re.compile(pattern, re.I) for pattern in [
        r"^pwd$", r"^ls(?:\s|$)", r"^git\s+(status|diff|log|show|rev-parse)(?:\s|$)",
        r"^(rg|grep|head|tail|wc)\s",
        r"^(python|python3)\s+-m\s+(pytest|unittest)(?:\s|$)", r"^pytest(?:\s|$)",
        r"^npm\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^pnpm\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^yarn\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^bun\s+(test|run\s+(test|lint|build|typecheck|check|dev|start))(?:\s|$)",
        r"^cargo\s+(test|check|build)(?:\s|$)", r"^go\s+test(?:\s|$)",
        r"^(npx\s+)?playwright\s+test(?:\s|$)", r"^ffprobe\s+[^;&|`<>]+$",
        r"^curl\s+[^;&|`]*https?://(127\.0\.0\.1|localhost)(:\d+)?(?:/[^\s]*)?(?:\s|$)",
    ]]
    EVIDENCE_INGEST = re.compile(
        r"^\.aah/bin/factory\s+evidence-ingest\s+RUN-[A-Za-z0-9._-]+\s+--file\s+[A-Za-z0-9_./-]+$"
    )

    def __init__(self, mode: str = "guarded"):
        self.mode = mode if mode in {"open", "guarded", "locked"} else "guarded"

    @staticmethod
    def normalize_role(role: str | None) -> str | None:
        if not role:
            return None
        value = role.strip().lower().replace("-", "_")
        return value[4:] if value.startswith("aah_") else value

    @staticmethod
    def _sensitive_command_text(command: str) -> bool:
        normalized = command.replace("\\", "/").lower()
        return any(token in normalized for token in [".env", "/.ssh/", "/.aws/", "/.config/gcloud/", "/.azure/", "/.kube/config"])

    def _artifact_role_command(self, command: str, role: str) -> CommandDecision:
        compact = command.strip()
        if self._sensitive_command_text(compact):
            return CommandDecision(Decision.BLOCK, f"{role} cannot access sensitive paths from shell")
        if self.EVIDENCE_INGEST.fullmatch(compact):
            if role in self.EVIDENCE_WRITER_ROLES:
                return CommandDecision(Decision.ALLOW, "runtime-controlled evidence ingestion")
            return CommandDecision(Decision.BLOCK, f"{role} cannot submit verification evidence")
        if any(token in compact for token in [";", "&&", "||", "`", "$(", ">", "<"]):
            return CommandDecision(Decision.BLOCK, f"{role} shell command is outside the verification allowlist")
        if any(pattern.search(compact) for pattern in self.REVIEW_SAFE_COMMANDS):
            return CommandDecision(Decision.ALLOW, "bounded verification command")
        return CommandDecision(Decision.BLOCK, f"{role} may only run bounded verification commands")

    def classify_command(self, command: str, role: str | None = None) -> CommandDecision:
        for pattern in self.UNIVERSAL_BLOCK:
            if pattern.search(command):
                return CommandDecision(Decision.BLOCK, "universal destructive action")
        normalized = self.normalize_role(role)
        compact = command.strip()
        if self.EVIDENCE_INGEST.fullmatch(compact):
            if normalized in self.EVIDENCE_WRITER_ROLES:
                return CommandDecision(Decision.ALLOW, "runtime-controlled evidence ingestion")
            return CommandDecision(Decision.BLOCK, "only verification roles may ingest evidence")
        if normalized in self.ARTIFACT_ONLY_ROLES:
            return self._artifact_role_command(command, normalized)
        if re.search(r"\b(curl|wget)\b[^|]*\|\s*(bash|sh)\b", command):
            if self.mode == "locked":
                return CommandDecision(Decision.BLOCK, "remote pipe-to-shell blocked in LOCKED")
            if self.mode == "guarded":
                return CommandDecision(Decision.REQUIRE_APPROVAL, "remote pipe-to-shell requires approval")
            return CommandDecision(Decision.WARN, "remote pipe-to-shell is risky")
        if any(pattern.search(command) for pattern in self.PROD_PATTERNS):
            if self.mode == "locked":
                return CommandDecision(Decision.REQUIRE_APPROVAL, "production-sensitive action")
            if self.mode == "guarded":
                return CommandDecision(Decision.WARN, "production-sensitive action")
        return CommandDecision(Decision.ALLOW, "routine command")

    @staticmethod
    def _resolve_inside(path: str, root: str | None) -> tuple[Path | None, str | None]:
        # Real regression found live (2026-08-08, rebasing
        # hardening/lite-pro-factory-v2 onto main): `root` is
        # typed `str | None = None` on can_write/can_read, but this used
        # to hard-require it (`if not path or not root: return None,
        # None`), which both callers signatures and this class's own
        # role-based logic (ROLE_RUN_WRITES, ARTIFACT_ONLY_ROLES etc. --
        # all keyed off the *relative* .aah/runs/... path, not an
        # absolute root) never actually needed. Every real production
        # caller (hook_guardian.py) does pass root, so this didn't show
        # up live, but any direct call without one (this class's own
        # test suite included) silently failed closed regardless of the
        # real role/path -- degrading gracefully to "treat path as
        # already relative" instead, matching the pre-rewrite behavior.
        if not path:
            return None, None
        raw = Path(path)
        if root:
            root_path = Path(root).resolve()
            resolved = (raw if raw.is_absolute() else root_path / raw).resolve()
            try:
                relative = resolved.relative_to(root_path)
            except ValueError:
                return resolved, None
            return resolved, relative.as_posix()
        if raw.is_absolute():
            return raw, None
        normalized = posixpath.normpath(raw.as_posix())
        if normalized == ".." or normalized.startswith("../"):
            return raw, None
        return raw, normalized

    @staticmethod
    def _env_path(relative: str) -> bool:
        name = Path(relative).name
        return name == ".env" or name.startswith(".env.")

    @staticmethod
    def _is_task_artifact(relative: str) -> bool:
        parts = Path(relative).parts
        return len(parts) >= 6 and parts[0] == ".aah" and parts[1] == "runs" and parts[3] == "tasks"

    def can_read(self, path: str, root: str | None = None) -> bool:
        resolved, relative = self._resolve_inside(path, root)
        if resolved is None or relative is None:
            return False
        absolute = resolved.as_posix()
        if self._env_path(relative):
            return False
        if any(token in absolute for token in self.SENSITIVE_HOME_PARTS):
            return False
        if relative.startswith(self.PROTECTED_READ_PREFIXES):
            return False
        return True

    def can_write(self, path: str, root: str | None = None, role: str | None = None) -> bool:
        resolved, relative = self._resolve_inside(path, root)
        if resolved is None or relative is None:
            return False
        absolute = resolved.as_posix()
        normalized = self.normalize_role(role)
        if self._env_path(relative):
            return False
        if any(token in absolute for token in self.SENSITIVE_HOME_PARTS):
            return False
        if relative.startswith(self.PROTECTED_WRITE_PREFIXES):
            return False
        if relative.startswith(".aah/") and not relative.startswith(".aah/runs/"):
            return False

        if relative.startswith(".aah/runs/"):
            task_path = self._is_task_artifact(relative)
            if normalized in self.TASK_ONLY_RUN_ROLES and not task_path:
                return False
            if normalized in self.ROOT_ONLY_RUN_ROLES and task_path:
                return False
            basename = Path(relative).name
            if basename in self.RUNTIME_OWNED_BASENAMES:
                return False
            all_owned = set().union(*self.ROLE_RUN_WRITES.values()) if self.ROLE_RUN_WRITES else set()
            allowed = self.ROLE_RUN_WRITES.get(normalized or "", set())
            if basename in all_owned:
                return basename in allowed
            return False

        if normalized in self.ARTIFACT_ONLY_ROLES:
            return False
        return True
