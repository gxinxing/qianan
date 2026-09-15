"""轨迹留痕：Agent 每一步（规划/工具调用/反思）写入 task.trace，供前端回放。

支持实时事件回调（SSE 推送）：设置 task._event_hook 后，record() 会同步调用该回调。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ..schemas import TaskRecord, TraceEvent

logger = logging.getLogger(__name__)

MAX_EVENTS = 60
SUMMARY_LIMIT = 200

# 全局事件钩子注册表：task_id -> async callback
_event_hooks: dict[str, Callable[[dict[str, Any]], Any]] = {}


def set_event_hook(task_id: str, hook: Callable[[dict[str, Any]], Any] | None) -> None:
    """注册/注销实时事件回调（SSE 推送用）。"""
    if hook is None:
        _event_hooks.pop(task_id, None)
    else:
        _event_hooks[task_id] = hook


def record(
    task: TaskRecord,
    phase: str,
    tool: str,
    args_summary: str = "",
    result_summary: str = "",
    status: str = "ok",
) -> None:
    """追加一条轨迹事件；超出上限后静默丢弃（防 trace 膨胀）。

    如果该 task 注册了事件钩子，会同步触发（用于 SSE 流式推送）。
    """
    evt = TraceEvent(
        phase=phase,
        tool=tool,
        args_summary=args_summary[:SUMMARY_LIMIT],
        result_summary=result_summary[:SUMMARY_LIMIT],
        status=status,
    )
    task.trace.append(evt)
    if len(task.trace) > MAX_EVENTS:
        task.trace = task.trace[-MAX_EVENTS:]

    # 实时事件推送（SSE）
    hook = _event_hooks.get(task.task_id)
    if hook:
        event_data = {
            "type": "trace",
            "phase": phase,
            "tool": tool,
            "args": args_summary[:SUMMARY_LIMIT],
            "result": result_summary[:SUMMARY_LIMIT],
            "status": status,
        }
        try:
            result = hook(event_data)
            if asyncio.iscoroutine(result):
                # 在事件循环中安全地 schedule
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    asyncio.run(result)
        except Exception:  # noqa: BLE001
            logger.debug("event hook error", exc_info=True)
