from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from .artifacts import ArtifactStore
from .taskgraph import TaskGraph, TaskGraphError
from .final_gate import FinalGate, normalize_findings
from .evidence import EvidenceStore
from .domains import gate_types


def _positive(run_dir: Path, labels: set[str]) -> bool:
    matched = [
        record for record in EvidenceStore(run_dir).all()
        if str(record.get("type") or record.get("kind") or "") in labels
    ]
    explicit = [record.get("ok") for record in matched if "ok" in record]
    return bool(explicit) and all(value is True for value in explicit)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate one sealed FACTORY task")
    parser.add_argument("run_id")
    parser.add_argument("--task", required=True)
    args = parser.parse_args(argv)
    target = Path(os.environ.get("AAH_TARGET_ROOT") or os.getcwd()).resolve()
    try:
        run = ArtifactStore(target).get_run(args.run_id)
        request_doc = ArtifactStore.read_json(run.run_dir, "REQUEST.json", {}) or {}
        domain = str(request_doc.get("domain") or "code")
        graph = TaskGraph(ArtifactStore.read_json(run.run_dir, "TASKS.json", None))
        task = graph.by_id.get(args.task)
        if not task:
            raise TaskGraphError(f"unknown task {args.task}")
    except (ValueError, FileNotFoundError, TaskGraphError) as exc:
        print(f"AAH task gate error: {exc}", file=sys.stderr)
        return 2

    task_dir = run.run_dir / "tasks" / task["id"]
    try:
        findings = json.loads((task_dir / "FINDINGS.json").read_text(encoding="utf-8"))
    except Exception:
        findings = []
    mandatory = []
    if task["profile"] == "pro":
        mandatory.append({
            "name": "task_technical_tests",
            "ok": _positive(task_dir, gate_types(domain, "pro_test")),
        })
    result = FinalGate(task_dir).evaluate(None, normalize_findings(findings), mandatory)
    print(json.dumps(result, indent=2))
    return 0 if result["done"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
