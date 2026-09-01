"""内存任务存储（Demo 阶段够用；正式版换 Redis）。"""
from __future__ import annotations

import uuid
from typing import Optional

from .schemas import GenerateRequest, TaskRecord

_TASKS: dict[str, TaskRecord] = {}


def create_task(request: GenerateRequest) -> TaskRecord:
    task = TaskRecord(task_id=uuid.uuid4().hex[:12], request=request)
    _TASKS[task.task_id] = task
    return task


def get_task(task_id: str) -> Optional[TaskRecord]:
    return _TASKS.get(task_id)


def list_tasks() -> list[TaskRecord]:
    return sorted(_TASKS.values(), key=lambda t: t.created_at, reverse=True)


def delete_task(task_id: str) -> bool:
    return _TASKS.pop(task_id, None) is not None
