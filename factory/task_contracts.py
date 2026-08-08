from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .contracts import seal_contract


def seed_task_contract(run_dir: Path | str, task: dict[str, Any]) -> Path:
    run_dir = Path(run_dir)
    task_id = str(task["id"])
    task_dir = run_dir / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "reports").mkdir(exist_ok=True)
    if (task_dir / "CONTRACT.json").exists():
        seal_contract(task_dir)
        return task_dir

    spec_lines = [
        f"# TASK SPEC — {task_id}", "",
        f"## Objective\n{task.get('title') or task_id}", "",
        f"## Profile\n{str(task['profile']).upper()}", "", "## Scope",
    ]
    scope = task.get("scope") or []
    spec_lines += [f"- {item}" for item in scope] if scope else ["- Use only the minimum project scope required by this task."]
    spec_lines += ["", "## Dependencies"]
    dependencies = task.get("depends_on") or []
    spec_lines += [f"- {item}" for item in dependencies] if dependencies else ["- None"]
    spec_lines += ["", "## Acceptance Criteria"]
    rubric = []
    for index, criterion in enumerate(task["acceptance"], start=1):
        criterion_id = f"{task_id}-R-{index:03d}"
        spec_lines.append(f"- {criterion_id}: {criterion}")
        rubric.append({"id": criterion_id, "required": True, "criterion": criterion})

    spec = "\n".join(spec_lines) + "\n"
    (task_dir / "TASK_SPEC.md").write_text(spec, encoding="utf-8")
    (task_dir / "SPEC.md").write_text(spec, encoding="utf-8")
    (task_dir / "RUBRIC.json").write_text(
        json.dumps({"criteria": rubric}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    seal_contract(task_dir)
    return task_dir
