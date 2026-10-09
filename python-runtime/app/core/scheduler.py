"""Deterministic dependency-aware scheduler primitives for Python core."""
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field, model_validator

class TaskStatus(str,Enum):
    PENDING="pending"; READY="ready"; RUNNING="running"; COMPLETED="completed"
    FAILED="failed"; CANCELLED="cancelled"; BLOCKED="blocked"

class ScheduledTask(BaseModel):
    task_id:str
    agent_id:str
    instruction:str
    dependencies:list[str]=Field(default_factory=list)
    status:TaskStatus=TaskStatus.PENDING
    attempt:int=0
    max_attempts:int=1
    result_ref:str|None=None
    error:str|None=None

class TaskPlan(BaseModel):
    tasks:dict[str,ScheduledTask]
    max_tasks:int=100

    @model_validator(mode="after")
    def validate_graph(self):
        if len(self.tasks)>self.max_tasks: raise ValueError(f"Task count exceeds limit {self.max_tasks}.")
        for key,t in self.tasks.items():
            if key!=t.task_id: raise ValueError(f"Task key {key!r} does not match task_id.")
            missing=set(t.dependencies)-set(self.tasks)
            if missing: raise ValueError(f"Task {key!r} has missing dependencies: {sorted(missing)}.")
            if key in t.dependencies: raise ValueError(f"Task {key!r} depends on itself.")
        visiting=set();visited=set()
        def visit(k):
            if k in visiting: raise ValueError(f"Dependency cycle detected at {k!r}.")
            if k in visited:return
            visiting.add(k)
            for dep in self.tasks[k].dependencies:visit(dep)
            visiting.remove(k);visited.add(k)
        for k in self.tasks:visit(k)
        return self

    def refresh_ready(self)->list[str]:
        ready=[]
        for t in self.tasks.values():
            if t.status!=TaskStatus.PENDING:continue
            states=[self.tasks[d].status for d in t.dependencies]
            if any(s in (TaskStatus.FAILED,TaskStatus.CANCELLED,TaskStatus.BLOCKED) for s in states):
                t.status=TaskStatus.BLOCKED;t.error="A prerequisite did not complete successfully."
            elif all(s==TaskStatus.COMPLETED for s in states):
                t.status=TaskStatus.READY;ready.append(t.task_id)
        return ready

    def claim_ready(self,limit:int)->list[ScheduledTask]:
        claimed=[]
        for t in self.tasks.values():
            if t.status==TaskStatus.READY and len(claimed)<max(0,limit):
                t.status=TaskStatus.RUNNING;t.attempt+=1;claimed.append(t)
        return claimed

    def complete(self,task_id:str,*,result_ref:str|None=None)->list[str]:
        t=self._get(task_id)
        if t.status!=TaskStatus.RUNNING:raise ValueError(f"Cannot complete {task_id!r} from {t.status.value}.")
        t.status=TaskStatus.COMPLETED;t.result_ref=result_ref;t.error=None
        return self.refresh_ready()

    def fail(self,task_id:str,error:str,*,retryable:bool=False)->list[str]:
        t=self._get(task_id)
        if t.status!=TaskStatus.RUNNING:raise ValueError(f"Cannot fail {task_id!r} from {t.status.value}.")
        t.error=error[:1000]
        t.status=TaskStatus.READY if retryable and t.attempt<t.max_attempts else TaskStatus.FAILED
        return self.refresh_ready()

    def cancel_pending(self)->None:
        for t in self.tasks.values():
            if t.status in (TaskStatus.PENDING,TaskStatus.READY):t.status=TaskStatus.CANCELLED

    def _get(self,task_id):
        if task_id not in self.tasks:raise KeyError(f"Unknown task_id {task_id!r}.")
        return self.tasks[task_id]

    @property
    def terminal(self)->bool:
        return all(t.status in (TaskStatus.COMPLETED,TaskStatus.FAILED,TaskStatus.CANCELLED,TaskStatus.BLOCKED) for t in self.tasks.values())

    @property
    def successful(self)->bool:
        return self.terminal and all(t.status==TaskStatus.COMPLETED for t in self.tasks.values())
