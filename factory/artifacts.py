from __future__ import annotations
import json, os, tempfile, re
from datetime import datetime
from pathlib import Path
from typing import Any
from .models import RunHandle


_RUN_ID_RE=re.compile(r"^RUN-[A-Za-z0-9][A-Za-z0-9._-]*$")


class ArtifactStore:
    def __init__(self, target: Path | str):
        self.target = Path(target).resolve()
        self.root = self.target / ".aah" / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        value=str(run_id)
        if not _RUN_ID_RE.fullmatch(value) or ".." in value or "/" in value or "\\" in value:
            raise ValueError(f"invalid run id: {run_id!r}")
        return value

    def _next_run_id(self) -> str:
        day = datetime.now().strftime("%Y%m%d")
        prefix = f"RUN-{day}-"
        nums = []
        for p in self.root.glob(prefix + "*"):
            try:
                nums.append(int(p.name.rsplit("-", 1)[1]))
            except Exception:
                pass
        return f"{prefix}{(max(nums, default=0)+1):03d}"

    def create_run(self, request: str, profile: str, guardian: str, domain: str, run_id: str | None = None) -> RunHandle:
        if run_id is not None:
            run_id=self._validate_run_id(run_id)
            run_dir=self.root/run_id
            run_dir.mkdir(parents=True,exist_ok=False)
        else:
            # Two local workers can race between ID calculation and mkdir. mkdir is the lock;
            # losers rescan and retry instead of crashing or sharing a run directory.
            for _ in range(1000):
                candidate=self._validate_run_id(self._next_run_id())
                run_dir=self.root/candidate
                try:
                    run_dir.mkdir(parents=True,exist_ok=False)
                    run_id=candidate
                    break
                except FileExistsError:
                    continue
            else:
                raise RuntimeError("unable to allocate a unique AAH run id")

        assert run_id is not None
        for name in ["logs", "screenshots", "artifacts"]:
            (run_dir / name).mkdir()
        self.write_json(run_dir, "REQUEST.json", {
            "request": request,
            "profile": profile,
            "guardian": guardian,
            "domain": domain,
            "created_at": datetime.now().astimezone().isoformat(),
        })
        self.write_json(run_dir, "STATE.json", {
            "run_id": run_id,
            "phase": "created",
            "profile": profile,
            "guardian": guardian,
            "domain": domain,
            "pass": 0,
            "status": "running",
            "history": [],
        })
        return RunHandle(run_id, run_dir)

    def get_run(self, run_id: str) -> RunHandle:
        run_id=self._validate_run_id(run_id)
        p = self.root / run_id
        if not p.is_dir():
            raise FileNotFoundError(run_id)
        return RunHandle(run_id, p)

    def latest_run(self) -> RunHandle | None:
        runs = sorted([p for p in self.root.iterdir() if p.is_dir() and _RUN_ID_RE.fullmatch(p.name)])
        return RunHandle(runs[-1].name, runs[-1]) if runs else None

    @staticmethod
    def _safe_path(run_dir: Path, name: str) -> Path:
        rel=Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"unsafe artifact path: {name}")
        path=(run_dir/rel).resolve()
        base=run_dir.resolve()
        if base not in path.parents and path!=base:
            raise ValueError(f"artifact escapes run dir: {name}")
        return path

    def write_json(self, run_dir: Path, name: str, data: Any) -> Path:
        path = self._safe_path(run_dir,name)
        self._atomic_write(path, json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")
        return path

    def write_text(self, run_dir: Path, name: str, text: str) -> Path:
        path = self._safe_path(run_dir,name)
        self._atomic_write(path, text if text.endswith("\n") else text + "\n")
        return path

    def append_jsonl(self, run_dir: Path, name: str, data: dict[str, Any]) -> Path:
        path = self._safe_path(run_dir,name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, sort_keys=True, default=str) + "\n")
        return path

    @staticmethod
    def read_json(run_dir: Path, name: str, default: Any = None) -> Any:
        path = ArtifactStore._safe_path(Path(run_dir),name)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
