"""test_swarm_evo_cancel.py — 取消信号传播测试。

验收：
  - run_pipeline 接受 should_stop 参数
  - should_stop 立即触发时任务被标记 cancelled
  - 黑板 cancelled 状态稳定（log_action 不重置）
  - asyncio.Event 可直接作 should_stop 工厂
"""
from __future__ import annotations

import asyncio

import pytest

# ---------------------------------------------------------------- 1. run_pipeline 签名接受 should_stop


def test_run_pipeline_accepts_should_stop():
    """run_pipeline 必须接受 should_stop 关键字参数（否则 mock 取消无法透传）。"""
    import inspect

    from app.orchestrator import run_pipeline

    sig = inspect.signature(run_pipeline)
    assert "should_stop" in sig.parameters, (
        "run_pipeline 缺少 should_stop 参数——mock 取消信号无法透传！"
    )


# ---------------------------------------------------------------- 2. run_pipeline should_stop 立即触发时取消


def test_run_pipeline_cancel_propagates():
    """should_stop 在首次检查时就返回 True，任务应被标记 cancelled。"""
    from app.orchestrator import run_pipeline
    from app.schemas import GenerateRequest, TaskStatus
    from app.task_store import create_task

    req = GenerateRequest(
        product_name="测试商品",
        selling_points="测试",
        category="home_kitchen",
        platforms=["amazon"],
    )

    task = create_task(req)

    async def _run():
        await run_pipeline(task, _MockClient(), should_stop=lambda: True)

    asyncio.run(_run())
    assert task.status == TaskStatus.cancelled


# ---------------------------------------------------------------- 3. 黑板 cancelled 状态不变为 running


def test_blackboard_cancel_status_stable():
    """一旦 status 被设为 cancelled，再调用 log_action 也不应改变 status。"""
    from app.agents.swarm.blackboard import Blackboard

    bb = Blackboard(["amazon"])
    bb.status = "cancelled"
    bb.log_action("some_action", "worker", True, "note")
    assert bb.status == "cancelled", "action 不应重置 cancelled 状态"


# ---------------------------------------------------------------- 4. asyncio.Event 取消模式


def test_cancel_via_event():
    """asyncio.Event.is_set 作为 should_stop，set() 后返回 True。"""
    async def _run():
        cancel_event = asyncio.Event()
        should_stop = cancel_event.is_set

        assert not should_stop()
        cancel_event.set()
        assert should_stop()

    asyncio.run(_run())


# ---------------------------------------------------------------- 5. 中途取消：阶段边界生效


def test_run_pipeline_cancel_midway():
    """should_stop 首次放行、第二次触发 → 任务在阶段边界被取消（非 done/partial/failed）。"""
    from app.orchestrator import run_pipeline
    from app.schemas import GenerateRequest, TaskStatus
    from app.task_store import create_task

    req = GenerateRequest(
        product_name="测试商品",
        selling_points="测试",
        category="home_kitchen",
        platforms=["amazon"],
    )
    task = create_task(req)

    n_checks: list[int] = []

    def _flip_after_first() -> bool:
        n_checks.append(1)
        return len(n_checks) > 1  # 第一次放行 → 跑过意图阶段；此后任一检查点触发取消

    async def _run():
        await run_pipeline(task, _MockClient(), should_stop=_flip_after_first)

    asyncio.run(_run())
    assert task.status == TaskStatus.cancelled, f"阶段边界取消应生效，实际 {task.status}"
    assert task.stage == "已取消"
    assert len(n_checks) >= 2, "pipeline 应有多个取消检查点，而非只在入口检查一次"


def test_run_pipeline_cancel_inside_gather():
    """取消信号在平台构建阶段（gather 内）触发 → 兄弟协程被撤销回收，仍得 cancelled 终态。"""
    from app.orchestrator import run_pipeline
    from app.schemas import GenerateRequest, TaskStatus
    from app.task_store import create_task

    req = GenerateRequest(
        product_name="测试商品",
        selling_points="测试",
        category="home_kitchen",
        platforms=["amazon", "shopee"],
    )
    task = create_task(req)

    n_checks: list[int] = []

    def _flip_after_three() -> bool:
        n_checks.append(1)
        return len(n_checks) > 3  # 1=入口 2=理解后 3=规则后；第 4 次 = 单平台文案完成后（gather 内）

    async def _run():
        await run_pipeline(task, _MockClient(), should_stop=_flip_after_three)

    asyncio.run(_run())
    assert task.status == TaskStatus.cancelled, f"gather 内取消应生效，实际 {task.status}"
    assert len(n_checks) >= 4, "取消应发生在 gather 内部的检查点"


# ---------------------------------------------------------------- Mock 客户端


class _MockClient:
    """最小化 mock 客户端，is_mock=True 触发 mock 分支。"""
    is_mock = True

    def chat_with_tools(self, messages, schemas):
        return {"content": "mock", "tool_calls": []}

    def chat(self, system, user):
        return "mock"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
