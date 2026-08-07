from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Any

class GitCheckpoints:
    def __init__(self,target:Path|str): self.target=Path(target).resolve()
    def _run(self,*args:str)->subprocess.CompletedProcess: return subprocess.run(["git","-C",str(self.target),*args],text=True,capture_output=True)
    def snapshot(self)->dict[str,Any]:
        if not (self.target/".git").exists(): return {"is_repo":False,"head":None,"dirty":False}
        h=self._run("rev-parse","HEAD"); s=self._run("status","--porcelain"); b=self._run("branch","--show-current")
        return {"is_repo":True,"head":h.stdout.strip() if h.returncode==0 else None,"dirty":bool(s.stdout.strip()),"branch":b.stdout.strip() if b.returncode==0 else None}
