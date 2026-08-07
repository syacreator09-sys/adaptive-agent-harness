from __future__ import annotations
from typing import Any

class TaskGraphError(ValueError): pass

class TaskGraph:
    def __init__(self,data:dict[str,Any]):
        self.tasks=data.get("tasks",[]) if isinstance(data,dict) else []
        self.by_id={str(t.get("id")):t for t in self.tasks}
        self.validate()
    def validate(self):
        if len(self.by_id)!=len(self.tasks): raise TaskGraphError("duplicate or missing task id")
        for t in self.tasks:
            for dep in t.get("depends_on",[]):
                if str(dep) not in self.by_id: raise TaskGraphError(f"unknown dependency {dep}")
        self.order()
    def order(self)->list[dict[str,Any]]:
        done=set(); ordered=[]
        while len(ordered)<len(self.tasks):
            ready=[t for t in self.tasks if str(t["id"]) not in done and all(str(d) in done for d in t.get("depends_on",[]))]
            if not ready: raise TaskGraphError("cycle detected")
            for t in ready: ordered.append(t); done.add(str(t["id"]))
        return ordered
