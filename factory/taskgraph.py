from __future__ import annotations
import re
from typing import Any


_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class TaskGraphError(ValueError):
    pass


class TaskGraph:
    def __init__(self, data: dict[str, Any]):
        if not isinstance(data, dict):
            raise TaskGraphError("task graph must be an object")
        tasks = data.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise TaskGraphError("task graph must contain at least one task")
        self.tasks: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}
        self._load(tasks)
        self.validate()

    def _load(self, tasks: list[Any]) -> None:
        for index, raw in enumerate(tasks):
            if not isinstance(raw, dict):
                raise TaskGraphError(f"task {index} must be an object")
            task = dict(raw)
            task_id = str(task.get("id") or "").strip()
            if not task_id or not _TASK_ID_RE.fullmatch(task_id):
                raise TaskGraphError(f"task {index} has invalid id {task_id!r}")
            if task_id in self.by_id:
                raise TaskGraphError(f"duplicate task id {task_id}")
            profile = str(task.get("profile") or "lite").lower()
            if profile not in {"lite", "pro"}:
                raise TaskGraphError(f"task {task_id} profile must be lite or pro")
            depends = task.get("depends_on", [])
            if not isinstance(depends, list):
                raise TaskGraphError(f"task {task_id} depends_on must be an array")
            acceptance = task.get("acceptance")
            if not isinstance(acceptance, list) or not [item for item in acceptance if str(item).strip()]:
                raise TaskGraphError(f"task {task_id} requires non-empty acceptance criteria")
            scope = task.get("scope", [])
            if scope is not None and not isinstance(scope, list):
                raise TaskGraphError(f"task {task_id} scope must be an array")
            task.update(
                {
                    "id": task_id,
                    "profile": profile,
                    "depends_on": [str(item) for item in depends],
                    "acceptance": [str(item).strip() for item in acceptance if str(item).strip()],
                    "scope": [str(item) for item in (scope or [])],
                }
            )
            self.tasks.append(task)
            self.by_id[task_id] = task

    def validate(self) -> bool:
        for task in self.tasks:
            for dependency in task["depends_on"]:
                if dependency not in self.by_id:
                    raise TaskGraphError(f"unknown dependency {dependency} for task {task['id']}")
                if dependency == task["id"]:
                    raise TaskGraphError(f"task {task['id']} cannot depend on itself")
        self.order()
        return True

    def order(self) -> list[dict[str, Any]]:
        done: set[str] = set()
        ordered: list[dict[str, Any]] = []
        while len(ordered) < len(self.tasks):
            ready = [
                task
                for task in self.tasks
                if task["id"] not in done and all(dependency in done for dependency in task["depends_on"])
            ]
            if not ready:
                unresolved = [task["id"] for task in self.tasks if task["id"] not in done]
                raise TaskGraphError(f"cycle detected among tasks: {unresolved}")
            for task in ready:
                ordered.append(task)
                done.add(task["id"])
        return ordered

    def ready(self, completed: set[str]) -> list[dict[str, Any]]:
        return [
            task for task in self.tasks
            if task["id"] not in completed and all(dependency in completed for dependency in task["depends_on"])
        ]
