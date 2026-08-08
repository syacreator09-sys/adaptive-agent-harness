from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Any


class GitCheckpoints:
    def __init__(self,target:Path|str):
        self.target=Path(target).resolve()

    def _run(self,*args:str)->subprocess.CompletedProcess:
        return subprocess.run(["git","-C",str(self.target),*args],text=True,capture_output=True)

    def snapshot(self)->dict[str,Any]:
        inside=self._run("rev-parse","--is-inside-work-tree")
        if inside.returncode!=0 or inside.stdout.strip()!="true":
            return {"is_repo":False,"head":None,"dirty":False}
        h=self._run("rev-parse","HEAD")
        s=self._run("status","--porcelain")
        b=self._run("branch","--show-current")
        git_dir=self._run("rev-parse","--git-dir")
        common_dir=self._run("rev-parse","--git-common-dir")
        gd=git_dir.stdout.strip() if git_dir.returncode==0 else None
        cd=common_dir.stdout.strip() if common_dir.returncode==0 else None
        return {
            "is_repo":True,
            "head":h.stdout.strip() if h.returncode==0 else None,
            "dirty":bool(s.stdout.strip()) if s.returncode==0 else False,
            "branch":b.stdout.strip() if b.returncode==0 else None,
            "git_dir":gd,
            "git_common_dir":cd,
            "is_linked_worktree":bool(gd and cd and gd!=cd),
        }
