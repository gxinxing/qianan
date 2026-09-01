"""轨迹留痕：Agent 每一步（规划/工具调用/反思）写入 task.trace，供前端回放。"""
from __future__ import annotations

from ..schemas import TaskRecord, TraceEvent

MAX_EVENTS = 60
SUMMARY_LIMIT = 200


def record(
    task: TaskRecord,
    phase: str,
    tool: str,
    args_summary: str = "",
    result_summary: str = "",
    status: str = "ok",
) -> None:
    """追加一条轨迹事件；超出上限后静默丢弃（防 trace 膨胀）。"""
    if len(task.trace) >= MAX_EVENTS:
        return
    task.trace.append(
        TraceEvent(
            phase=phase,
            tool=tool,
            args_summary=args_summary[:SUMMARY_LIMIT],
            result_summary=result_summary[:SUMMARY_LIMIT],
            status=status,
        )
    )
