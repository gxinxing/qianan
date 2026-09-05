"""任务存储 —— 内存为主 + 归属关系落盘（多租户）。

内存任务在重启后会丢，但**归属关系**（task_id → owner_uid）会持久化到
`data/owners.json`，这样从磁盘文件仓库还原出来的任务仍然受租户隔离保护：
匿名访问者读不到登录用户的历史包，反之亦然。
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from .schemas import GenerateRequest, TaskRecord

logger = logging.getLogger(__name__)

_TASKS: dict[str, TaskRecord] = {}

#: 归属关系的持久化文件（与 file_store 的 data/tasks 同级）
_OWNERS_FILE = Path(__file__).resolve().parents[1] / "data" / "owners.json"
_OWNERS: dict[str, str] = {}
_OWNERS_LOADED = False


# ---------- 归属关系持久化 ----------

def _load_owners() -> None:
    global _OWNERS, _OWNERS_LOADED
    if _OWNERS_LOADED:
        return
    _OWNERS_LOADED = True
    try:
        if _OWNERS_FILE.exists():
            data = json.loads(_OWNERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _OWNERS = {str(k): str(v) for k, v in data.items()}
    except Exception:  # noqa: BLE001 —— 归属文件损坏不能拖垮启动
        logger.exception("owners.json 读取失败，按空归属继续")


def _save_owners() -> None:
    try:
        _OWNERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _OWNERS_FILE.write_text(
            json.dumps(_OWNERS, ensure_ascii=False, indent=0), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 —— 云函数只读目录下写不进去，降级为仅内存
        logger.warning("owners.json 写入失败（只读文件系统？），归属关系仅保留在本次实例内")


def bind_owner(task_id: str, owner_uid: str) -> None:
    _load_owners()
    _OWNERS[task_id] = owner_uid or "anonymous"
    _save_owners()


def owner_of(task_id: str) -> Optional[str]:
    """任务归属 uid；未登记返回 None（历史数据默认不可跨租户访问）。"""
    _load_owners()
    task = _TASKS.get(task_id)
    if task is not None and task.owner_uid:
        return task.owner_uid
    return _OWNERS.get(task_id)


def visible_to(task_id: str, uid: str) -> bool:
    """该 uid 能否访问此任务。未登记归属的历史包对所有登录用户可见（管理员视角）。"""
    owner = owner_of(task_id)
    if owner is None:
        return True
    return owner == uid


def tasks_of(uid: str) -> list[str]:
    """某租户的全部 task_id（含已落盘但内存已释放的）。"""
    _load_owners()
    ids = {t.task_id for t in _TASKS.values() if t.owner_uid == uid}
    ids |= {tid for tid, o in _OWNERS.items() if o == uid}
    return list(ids)


# ---------- 基础 CRUD ----------

def create_task(request: GenerateRequest, owner_uid: str = "") -> TaskRecord:
    task = TaskRecord(
        task_id=uuid.uuid4().hex[:12],
        request=request,
        owner_uid=owner_uid or "anonymous",
    )
    _TASKS[task.task_id] = task
    bind_owner(task.task_id, task.owner_uid)
    return task


def get_task(task_id: str) -> Optional[TaskRecord]:
    return _TASKS.get(task_id)


def list_tasks(owner_uid: Optional[str] = None) -> list[TaskRecord]:
    tasks = _TASKS.values()
    if owner_uid:
        tasks = [t for t in tasks if t.owner_uid == owner_uid]
    return sorted(tasks, key=lambda t: t.created_at, reverse=True)


def delete_task(task_id: str) -> bool:
    _load_owners()
    _OWNERS.pop(task_id, None)
    _save_owners()
    return _TASKS.pop(task_id, None) is not None
