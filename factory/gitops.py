from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Any


class GitCheckpoints:
    def __init__(self, target: Path | str):
        self.target = Path(target).resolve()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.target), *args],
            text=True,
            capture_output=True,
        )

    def is_repo(self) -> bool:
        result = self._run("rev-parse", "--is-inside-work-tree")
        return result.returncode == 0 and result.stdout.strip() == "true"

    def snapshot(self) -> dict[str, Any]:
        if not self.is_repo():
            return {"is_repo": False, "head": None, "dirty": False, "branch": None, "is_linked_worktree": False}
        head = self._run("rev-parse", "HEAD")
        status = self._run("status", "--porcelain")
        branch = self._run("branch", "--show-current")
        git_dir = self._run("rev-parse", "--git-dir")
        common_dir = self._run("rev-parse", "--git-common-dir")
        return {
            "is_repo": True,
            "head": head.stdout.strip() if head.returncode == 0 else None,
            "dirty": bool(status.stdout.strip()),
            "branch": branch.stdout.strip() if branch.returncode == 0 else None,
            "is_linked_worktree": (
                git_dir.returncode == 0
                and common_dir.returncode == 0
                and git_dir.stdout.strip() != common_dir.stdout.strip()
            ),
        }

    def planning_checkpoint(self, run_id: str) -> dict[str, Any]:
        """Create a durable pre-build boundary without committing user changes."""
        before = self.snapshot()
        if not before.get("is_repo"):
            return {"created": False, "reason": "not_git_repo", "head": None}
        if before.get("dirty"):
            return {"created": False, "reason": "dirty_baseline", "head": before.get("head")}
        commit = self._run("commit", "--allow-empty", "-m", f"aah(spec): seal {run_id}")
        after = self.snapshot()
        if commit.returncode != 0:
            return {
                "created": False,
                "reason": "commit_failed",
                "detail": (commit.stderr or commit.stdout).strip()[:500],
                "head": before.get("head"),
            }
        return {
            "created": True,
            "reason": "sealed",
            "head": after.get("head"),
            "previous_head": before.get("head"),
        }

    def has_finding_commit(
        self,
        finding_id: str,
        since: str | None = None,
        max_commits: int = 200,
    ) -> bool:
        if not self.is_repo() or not finding_id:
            return False
        args = ["log", f"-n{max_commits}", "--format=%s"]
        if since:
            check = self._run("cat-file", "-e", f"{since}^{{commit}}")
            if check.returncode == 0:
                args.append(f"{since}..HEAD")
        result = self._run(*args)
        if result.returncode != 0:
            return False
        needle = str(finding_id).lower()
        return any(needle in line.lower() for line in result.stdout.splitlines())
