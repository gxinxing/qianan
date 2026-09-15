"""多 Agent 蜂群（swarm）入口。

架构：一个主控（Supervisor）带着两类执行 agent ——
    PlatformWorker  负责文案与视觉素材
    ReviewWorker    负责独立审核（上下文隔离，不看写作者推理）

启用方式：环境变量 `QIANAN_SWARM=1`。
**默认关闭** —— 走原来的 `run_chat_agent` 工具循环，演示路径零风险。
"""
from __future__ import annotations

import logging
from typing import Any

from ...bailian.client import BailianLike
from ...schemas import GenerateRequest, TaskRecord
from .blackboard import ActionSpec, Blackboard
from .supervisor import Supervisor

logger = logging.getLogger(__name__)

__all__ = ["ActionSpec", "Blackboard", "Supervisor", "run_swarm"]


async def run_swarm(
    task: TaskRecord,
    client: BailianLike,
    req: GenerateRequest,
    on_event=None,
    should_stop=None,
) -> dict:
    """用主控 + 执行 agent 的方式跑一次上架任务，结果写回 task。

    返回 Supervisor.run 的原始结果，便于测试与回放。
    should_stop：取消信号，一路传到主控的工具循环。
    """
    from ...agent_core.trace import record

    bb = Blackboard(list(req.platforms), goal="full_package")
    supervisor = Supervisor(client, bb)

    def _emit(kind: str, payload: Any) -> None:
        if on_event:
            try:
                on_event(kind, payload)
            except Exception:  # noqa: BLE001 —— 事件推送失败不影响主流程
                logger.warning("swarm 事件推送失败: %s", kind)

    record(task, "plan", "swarm_init", bb.project_id,
           f"主控 + {len(bb.platforms)} 平台执行 agent")
    _emit("text", f"已组建 {len(bb.platforms)} 个平台执行 agent，主控开始调度。")

    try:
        result = await supervisor.run(req, task, should_stop=should_stop)
    except Exception as exc:  # noqa: BLE001 —— 蜂群整体失败要落到 task 上而不是炸掉请求
        logger.exception("swarm 执行失败")
        bb.status = "failed"
        bb.last_error = f"{type(exc).__name__}: {exc}"
        result = {
            "status": "failed",
            "listings": list(supervisor.listings.values()),
            "blackboard": bb.snapshot(),
            "actions": bb.action_history,
            "fallback": True,
            "reason": bb.last_error,
            "cancelled": False,
        }

    # ---- 结果写回 task ----
    listings = result.get("listings") or []
    if listings:
        task.listings = listings
    if task.plan is not None and task.plan.strategy == "":
        task.plan.strategy = "多 Agent 蜂群：主控调度 + 平台执行 agent"

    # 把动作历史落成结构化留痕（评审可回放：谁在什么时候做了什么）
    for a in bb.action_history:
        if a["actor"] == "guard":
            record(task, "guard", a["action"], "拒绝执行", a["note"], "warn")
        else:
            record(task, "build", a["action"], str(a["seq"]), a["note"])

    status = Supervisor.to_task_status(bb.status)
    task.status = status
    task.progress = 1.0 if status.value == "done" else 0.9

    if status.value == "done":
        task.stage = "完成"
        _emit("done", f"已完成 {len(listings)} 个平台的上架包，全部通过审核。")
    elif status.value == "partial":
        unfinished = [p for p, s in bb.platforms.items() if not (s.review_valid and not s.blocking_issues)]
        task.stage = f"部分完成（{len(listings)}/{len(bb.platforms)} 平台达标）"
        task.error = f"未达标平台：{', '.join(unfinished)}" if unfinished else bb.last_error
        _emit("done", f"只完成 {len(listings)}/{len(bb.platforms)} 个平台，未达到交付标准。")
    elif status.value == "cancelled":
        task.stage = "已取消"
        _emit("done", "已停止，已生成的内容已保留。")
    else:
        task.stage = "失败"
        task.error = bb.last_error or "蜂群执行失败"
        _emit("error", task.error)

    return result
