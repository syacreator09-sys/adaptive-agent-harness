from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from .envs import EnvRouter
from .mcp import MCPDiscovery


class ProjectAdapter:
    STACK_FILES = {
        "node": ["package.json"],
        "python": ["pyproject.toml", "requirements.txt", "setup.py"],
        "docker": ["Dockerfile", "compose.yaml", "docker-compose.yml"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
        "php": ["composer.json"],
        "ruby": ["Gemfile"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    }
    INSTRUCTION_FILES = [
        "CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "README.md", "SECURITY.md",
    ]

    def __init__(self, target: Path | str):
        self.target = Path(target).resolve()

    def _env_names(self) -> tuple[list[str], dict[str, str], list[str]]:
        names: set[str] = set()
        classes: dict[str, str] = {}
        files: list[str] = []
        for path in self.target.glob(".env*"):
            files.append(path.name)
            if not path.is_file():
                continue
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    name = stripped.split("=", 1)[0].strip()
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                        names.add(name)
                        classes[name] = EnvRouter.classify_name(name)
            except OSError:
                pass
        return sorted(names), classes, sorted(files)

    def _package_scripts(self) -> dict[str, str]:
        path = self.target / "package.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            return {str(key): str(value) for key, value in scripts.items()} if isinstance(scripts, dict) else {}
        except Exception:
            return {}

    def _commands(self) -> dict[str, str]:
        scripts = self._package_scripts()
        result: dict[str, str] = {}
        package_manager = "npm"
        if (self.target / "pnpm-lock.yaml").exists():
            package_manager = "pnpm"
        elif (self.target / "yarn.lock").exists():
            package_manager = "yarn"
        elif (self.target / "bun.lockb").exists() or (self.target / "bun.lock").exists():
            package_manager = "bun"

        for key in ["test", "build", "lint", "typecheck", "check", "dev", "start"]:
            if key in scripts:
                result[key] = f"{package_manager} run {key}"

        python_project = any((self.target / filename).exists() for filename in self.STACK_FILES["python"])
        if python_project and ((self.target / "pytest.ini").exists() or (self.target / "tests").exists()):
            result.setdefault("test", "python -m pytest")
        if (self.target / "go.mod").exists():
            result.setdefault("test", "go test ./...")
        if (self.target / "Cargo.toml").exists():
            result.setdefault("test", "cargo test")
        return result

    def _git_info(self) -> dict[str, Any]:
        def run(*args: str) -> str | None:
            try:
                cp = subprocess.run(
                    ["git", "-C", str(self.target), *args],
                    text=True,
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                return None
            return cp.stdout.strip() if cp.returncode == 0 else None

        inside = run("rev-parse", "--is-inside-work-tree")
        if inside != "true":
            return {"is_repo": False}
        status = run("status", "--porcelain") or ""
        git_dir = run("rev-parse", "--git-dir")
        common_dir = run("rev-parse", "--git-common-dir")
        return {
            "is_repo": True,
            "branch": run("branch", "--show-current"),
            "head": run("rev-parse", "HEAD"),
            "dirty": bool(status),
            "is_linked_worktree": bool(git_dir and common_dir and git_dir != common_dir),
        }

    def inspect(self) -> dict[str, Any]:
        stacks = [
            stack for stack, files in self.STACK_FILES.items()
            if any((self.target / filename).exists() for filename in files)
        ]
        env_names, env_classes, env_files = self._env_names()
        instructions = [filename for filename in self.INSTRUCTION_FILES if (self.target / filename).exists()]
        manifests = [
            name for name in [
                "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod",
                "compose.yaml", "docker-compose.yml", "Dockerfile", ".mcp.json",
            ]
            if (self.target / name).exists()
        ]
        mcp = MCPDiscovery(self.target).inspect()
        return {
            "root": str(self.target),
            "stacks": stacks,
            "manifests": manifests,
            "instruction_files": instructions,
            "env_names": env_names,
            "env_classes": env_classes,
            "env_files": env_files,
            "env_policy": {
                "persist_values": False,
                "secret_names_require_explicit_task_access": True,
            },
            "package_scripts": self._package_scripts(),
            "commands": self._commands(),
            "git": self._git_info(),
            "mcp": mcp,
            "existing_project": any(self.target.iterdir()) if self.target.exists() else False,
        }
