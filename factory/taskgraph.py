from __future__ import annotations
from typing import Any


class TaskGraphError(ValueError):
    pass


class TaskGraph:
    def __init__(self,data:dict[str,Any]):
        if not isinstance(data,dict):
            raise TaskGraphError("task graph must be an object")
        tasks=data.get("tasks")
        if not isinstance(tasks,list) or not tasks:
            raise TaskGraphError("task graph must contain at least one task")
        self.tasks=tasks
        self.by_id: dict[str,dict[str,Any]]={}
        self.validate()

    def validate(self):
        for index,task in enumerate(self.tasks):
            if not isinstance(task,dict):
                raise TaskGraphError(f"task {index} must be an object")
            raw_id=task.get("id")
            if raw_id is None or not str(raw_id).strip():
                raise TaskGraphError(f"task {index} is missing id")
            task_id=str(raw_id).strip()
            if task_id in self.by_id:
                raise TaskGraphError(f"duplicate task id {task_id}")
            task["id"]=task_id
            profile=str(task.get("profile","lite")).lower()
            if profile not in {"lite","pro"}:
                raise TaskGraphError(f"task {task_id} has invalid profile {profile}")
            task["profile"]=profile
            deps=task.get("depends_on",[])
            if not isinstance(deps,list):
                raise TaskGraphError(f"task {task_id} depends_on must be a list")
            task["depends_on"]=[str(dep) for dep in deps]
            acceptance=task.get("acceptance")
            if not isinstance(acceptance,list) or not [x for x in acceptance if str(x).strip()]:
                raise TaskGraphError(f"task {task_id} requires non-empty acceptance criteria")
            task["acceptance"]=[str(x).strip() for x in acceptance if str(x).strip()]
            self.by_id[task_id]=task

        for task in self.tasks:
            for dep in task["depends_on"]:
                if dep not in self.by_id:
                    raise TaskGraphError(f"unknown dependency {dep} for task {task['id']}")
                if dep==task["id"]:
                    raise TaskGraphError(f"task {task['id']} cannot depend on itself")
        self.order()
        return True

    def order(self)->list[dict[str,Any]]:
        done=set(); ordered=[]
        while len(ordered)<len(self.tasks):
            ready=[
                task for task in self.tasks
                if task["id"] not in done and all(dep in done for dep in task["depends_on"])
            ]
            if not ready:
                unresolved=[task["id"] for task in self.tasks if task["id"] not in done]
                raise TaskGraphError(f"cycle detected among tasks: {unresolved}")
            for task in ready:
                ordered.append(task)
                done.add(task["id"])
        return ordered
