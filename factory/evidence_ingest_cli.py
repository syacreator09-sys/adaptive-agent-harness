from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from .artifacts import ArtifactStore
from .evidence import EvidenceStore


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest verifier evidence into an AAH run/task")
    parser.add_argument("run_id")
    parser.add_argument("--file", required=True)
    args = parser.parse_args(argv)

    target = Path(os.environ.get("AAH_TARGET_ROOT") or os.getcwd()).resolve()
    try:
        run = ArtifactStore(target).get_run(args.run_id)
    except (ValueError, FileNotFoundError) as exc:
        print(f"AAH evidence error: {exc}", file=sys.stderr)
        return 2

    draft = Path(args.file)
    draft = (target / draft).resolve() if not draft.is_absolute() else draft.resolve()
    if not _inside(draft, run.run_dir) or draft.name != "EVIDENCE_DRAFT.json":
        print("AAH evidence error: draft must be EVIDENCE_DRAFT.json inside the selected run", file=sys.stderr)
        return 2
    evidence_root = draft.parent
    if not (evidence_root / "CONTRACT.json").exists():
        print("AAH evidence error: evidence target has no sealed CONTRACT.json", file=sys.stderr)
        return 2
    if not draft.is_file():
        print("AAH evidence error: draft file not found", file=sys.stderr)
        return 2
    try:
        value = json.loads(draft.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"AAH evidence error: invalid draft JSON: {exc}", file=sys.stderr)
        return 2
    records = value if isinstance(value, list) else [value]
    if not records or not all(isinstance(record, dict) for record in records):
        print("AAH evidence error: draft must be an evidence object or array of objects", file=sys.stderr)
        return 2

    store = EvidenceStore(evidence_root)
    written = [store.append(record) for record in records]
    draft.unlink()
    print(json.dumps({"ok": True, "count": len(written), "ids": [record["id"] for record in written]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
