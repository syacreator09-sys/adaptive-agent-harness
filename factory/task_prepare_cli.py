from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from .artifacts import ArtifactStore
from .taskgraph import TaskGraph, TaskGraphError
from .task_contracts import seed_task_contract
from .events import EventJournal


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate FACTORY DAG and seed sealed task contracts")
    parser.add_argument("run_id")
    args = parser.parse_args(argv)
    target = Path(os.environ.get("AAH_TARGET_ROOT") or os.getcwd()).resolve()
    try:
        run = ArtifactStore(target).get_run(args.run_id)
        raw = ArtifactStore.read_json(run.run_dir, "TASKS.json", None)
        graph = TaskGraph(raw)
    except (ValueError, FileNotFoundError, TaskGraphError) as exc:
        print(f"AAH task preparation error: {exc}", file=sys.stderr)
        return 2

    prepared = []
    for task in graph.tasks:
        task_dir = seed_task_contract(run.run_dir, task)
        prepared.append({
            "id": task["id"],
            "profile": task["profile"],
            "task_dir": str(task_dir),
            "depends_on": task["depends_on"],
        })
        EventJournal(run.run_dir).append(
            "TASK_CONTRACT_SEALED",
            task_id=task["id"],
            profile=task["profile"],
            criteria=len(task["acceptance"]),
            native_bridge=True,
        )
    print(json.dumps({"ok": True, "tasks": prepared}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
