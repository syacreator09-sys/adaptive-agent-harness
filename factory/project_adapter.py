from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from typing import Any
from .envs import EnvRouter


class ProjectAdapter:
    STACK_FILES = {
        "node": ["package.json"],
        "python": ["pyproject.toml","requirements.txt","setup.py"],
        "docker": ["Dockerfile","compose.yaml","docker-compose.yml"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
        "php": ["composer.json"],
        "ruby": ["Gemfile"],
        "java": ["pom.xml","build.gradle","build.gradle.kts"],
    }
    INSTRUCTION_FILES = ["CLAUDE.md","AGENTS.md","CONTRIBUTING.md","README.md","SECURITY.md"]

    def __init__(self, target: Path | str):
        self.target = Path(target).resolve()

    def _env_names(self) -> tuple[list[str], dict[str,str], list[str]]:
        names: set[str] = set(); classes: dict[str,str] = {}; files=[]
        for p in self.target.glob(".env*"):
            files.append(p.name)
            if not p.is_file():
                continue
            try:
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s=line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    name=s.split("=",1)[0].strip()
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                        names.add(name); classes[name]=EnvRouter.classify_name(name)
            except OSError:
                pass
        return sorted(names), classes, sorted(files)

    def _package_scripts(self) -> dict[str,str]:
        p=self.target/"package.json"
        if not p.exists():
            return {}
        try:
            data=json.loads(p.read_text(encoding="utf-8")); scripts=data.get("scripts",{})
            return {str(k):str(v) for k,v in scripts.items()} if isinstance(scripts,dict) else {}
        except Exception:
            return {}

    def _detected_stacks(self) -> list[str]:
        return [stack for stack,files in self.STACK_FILES.items() if any((self.target/f).exists() for f in files)]

    def _commands(self) -> dict[str,str]:
        scripts=self._package_scripts(); result={}
        for key in ["test","build","lint","typecheck","dev","start"]:
            if key in scripts:
                result[key]=f"npm run {key}"
        if "python" in self._detected_stacks():
            if (self.target/"pytest.ini").exists() or (self.target/"tests").exists():
                result.setdefault("test","python -m pytest")
        if (self.target/"go.mod").exists():
            result.setdefault("test","go test ./...")
        if (self.target/"Cargo.toml").exists():
            result.setdefault("test","cargo test")
        return result

    def _git_info(self) -> dict[str,Any]:
        def run(*args: str) -> str | None:
            try:
                cp=subprocess.run(["git","-C",str(self.target),*args],text=True,capture_output=True,timeout=5)
            except Exception:
                return None
            return cp.stdout.strip() if cp.returncode==0 else None

        inside=run("rev-parse","--is-inside-work-tree")
        if inside!="true":
            return {"is_repo":False}
        status=run("status","--porcelain") or ""
        git_dir=run("rev-parse","--git-dir")
        common_dir=run("rev-parse","--git-common-dir")
        return {
            "is_repo":True,
            "branch":run("branch","--show-current"),
            "head":run("rev-parse","HEAD"),
            "dirty":bool(status),
            "git_dir":git_dir,
            "git_common_dir":common_dir,
            "is_linked_worktree":bool(git_dir and common_dir and git_dir!=common_dir),
        }

    def inspect(self) -> dict[str,Any]:
        stacks=self._detected_stacks()
        env_names, env_classes, env_files=self._env_names()
        instructions=[f for f in self.INSTRUCTION_FILES if (self.target/f).exists()]
        manifests=[]
        for name in ["package.json","pyproject.toml","requirements.txt","Cargo.toml","go.mod","compose.yaml","docker-compose.yml","Dockerfile"]:
            if (self.target/name).exists():
                manifests.append(name)
        return {
            "root": str(self.target),
            "stacks": stacks,
            "manifests": manifests,
            "instruction_files": instructions,
            "env_names": env_names,
            "env_classes": env_classes,
            "env_files": env_files,
            "env_policy": {"persist_values": False, "secret_names_require_explicit_task_access": True},
            "package_scripts": self._package_scripts(),
            "commands": self._commands(),
            "git": self._git_info(),
            "existing_project": any(self.target.iterdir()) if self.target.exists() else False,
        }
