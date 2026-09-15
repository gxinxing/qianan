"""多 Agent 蜂群的核心不变量测试。

重点不是"能不能跑完"，而是三件决定它是 agent 而非 pipeline 的事：
  1. 下一件事做什么，是**模型在运行时选的**（换一个动作序列就换一条路径）
  2. 这一步**是否允许执行**，由代码判定（模型违规会被拒绝）
  3. 审核结论会随产物失效（改过就必须重审，否则不能交付）
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.agents.swarm.blackboard import ActionSpec, Blackboard
from app.schemas import ComplianceIssue, PlatformListing, TaskStatus
from app.agents.swarm.supervisor import Supervisor


# ---------------------------------------------------------------- 替身客户端


class ScriptedClient:
    """按脚本返回 tool_calls 的假客户端，用来模拟「模型的选择」。

    同时记录发给模型的工具清单，以验证动作表真的暴露给了模型。
    """

    is_mock = False

    def __init__(self, script: list[list[str]] | None = None) -> None:
        self.script = list(script or [])
        self.seen_tools: list[str] = []
        self.calls = 0

    def chat_with_tools(self, messages: list[dict], schemas: list[dict]) -> dict:
        self.calls += 1
        if schemas and not self.seen_tools:
            self.seen_tools = [s["function"]["name"] for s in schemas]
        if not self.script:
            return {"content": "收敛", "tool_calls": []}
        names = self.script.pop(0)
        return {
            "content": "",
            "tool_calls": [
                {"id": f"c{i}", "function": {"name": n, "arguments": "{}"}}
                for i, n in enumerate(names)
            ],
        }


def _listing(platform: str, **kw) -> PlatformListing:
    return PlatformListing(
        platform=platform,
        display_name=platform.upper(),
        title=kw.get("title", "Portable Blender"),
        bullets=kw.get("bullets", ["Fast"]),
        description="d",
        images=kw.get("images", ["http://img/m.jpg"]),
    )


def _req() -> Any:
    from app.schemas import GenerateRequest

    return GenerateRequest(
        product_name="便携榨汁杯",
        selling_points="USB-C 快充",
        category="home_kitchen",
        platforms=["amazon", "shopee"],
    )


# ------------------------------------------------- 1. 模型选择驱动执行路径


def test_action_table_is_exposed_to_model():
    """动作表必须完整暴露给模型，否则它无从选择。"""
    bb = Blackboard(["amazon", "shopee"])
    sup = Supervisor(ScriptedClient(), bb)
    names = [a.name for a in sup.action_table()]
    # 1 个全局动作 + 每平台 5 个 + 1 个交付
    assert names.count("generate_copy") == 2
    assert names.count("review_listing") == 2
    assert "understand_product" in names
    assert names[-1] == "submit_deliverable"


def test_different_scripts_produce_different_paths():
    """路径敏感性：模型换一个选择序列，动作历史就不同。

    这正是「pipeline vs agent」的分水岭 —— 硬编码流水线的动作序列恒定。
    """
    script_a = [
        ["understand_product"],
        ["generate_copy__amazon", "generate_copy__shopee"],
        ["review_listing__amazon"],
    ]
    script_b = [
        ["understand_product"],
        ["generate_images__amazon"],  # 换个选择：先出图
        ["generate_copy__amazon"],
    ]
    hist_a = asyncio.run(_run_with(script_a))
    hist_b = asyncio.run(_run_with(script_b))
    assert hist_a != hist_b, "不同模型选择必须产生不同动作序列"
    assert [h["action"] for h in hist_a][:1] == ["understand_product"]


async def _run_with(script: list[list[str]]) -> list[dict]:
    bb = Blackboard(["amazon", "shopee"])
    sup = Supervisor(ScriptedClient(script), bb)
    # 跳过真实生成：只验证调度与守卫
    sup._act_understand = _noop_understand  # type: ignore[method-assign]
    sup._act_copy = _noop_copy  # type: ignore[method-assign]
    sup._act_review = _noop_review  # type: ignore[method-assign]
    sup._act_images = _noop_images  # type: ignore[method-assign]
    await sup.run(_req())
    return bb.action_history


async def _noop_understand(req):  # noqa: ANN001
    return "ok"


async def _noop_copy(req, platform):  # noqa: ANN001
    return "ok"


async def _noop_review(platform, category):  # noqa: ANN001
    return "ok"


async def _noop_images(platform):  # noqa: ANN001
    return "ok"


# ------------------------------------------------- 2. 代码判定：违规被拒绝


def test_guard_rejects_delivery_before_copy_ready():
    """模型第一步就想交付 → 被前置条件拒绝，且状态不会变成 completed。"""
    bb = Blackboard(["amazon"])
    sup = Supervisor(ScriptedClient([["submit_deliverable"]]), bb)
    sup._act_understand = _noop_understand  # type: ignore[method-assign]
    sup._act_copy = _noop_copy  # type: ignore[method-assign]
    sup._act_review = _noop_review  # type: ignore[method-assign]
    asyncio.run(sup.run(_req()))

    rejected = [a for a in bb.action_history if a["action"] == "submit_deliverable"]
    assert rejected, "应当有一次交付尝试被记录"
    assert rejected[0]["ok"] is False
    assert rejected[0]["actor"] == "guard", "必须是代码守卫拒绝的，不是模型自觉放弃"
    assert bb.status != "completed"


def test_guard_rejects_review_before_copy():
    """没有文案就审核 → 拒绝。"""
    bb = Blackboard(["amazon"])
    spec = ActionSpec("review_listing", "", preconditions=["copy.amazon.ready"])
    assert spec.available(bb) is False
    bb.mark_copy("amazon")
    assert spec.available(bb) is True


# ------------------------------------------------- 3. 审核失效（验收标准 6）


def test_review_invalidated_by_copy_change():
    """改文案后审核立即失效；不改则保持有效。"""
    bb = Blackboard(["amazon"])
    bb.mark_copy("amazon")
    bb.mark_reviewed("amazon", [])
    assert bb.platforms["amazon"].review_valid is True

    bb.mark_copy("amazon")  # 修订文案
    assert bb.platforms["amazon"].review_valid is False

    bb.mark_reviewed("amazon", [])
    assert bb.platforms["amazon"].review_valid is True


def test_delivery_blocked_while_any_platform_unreviewed():
    """一个平台没审核，整个交付就被阻塞。"""
    bb = Blackboard(["amazon", "shopee"])
    for p in ("amazon", "shopee"):
        bb.mark_copy(p)
    bb.mark_reviewed("amazon", [])
    spec = ActionSpec(
        "submit_deliverable", "",
        preconditions=["all.copy.ready", "all.review.valid", "no.blocking"],
    )
    assert spec.available(bb) is False
    assert spec.blocked_by(bb) == ["all.review.valid"]

    bb.mark_reviewed("shopee", [])
    assert spec.available(bb) is True


def test_blocking_issue_blocks_delivery():
    """存在阻断级 error → 不可交付。"""
    bb = Blackboard(["amazon"])
    bb.mark_copy("amazon")
    bb.mark_reviewed("amazon", [{"severity": "error", "field": "title"}])
    assert bb.platforms["amazon"].blocking_issues
    spec = ActionSpec("submit_deliverable", "", preconditions=["no.blocking"])
    assert spec.available(bb) is False


# ------------------------------------------------- 4. 状态映射与降级


def test_status_mapping_covers_all_outcomes():
    """黑板状态必须能映射到任务状态，且未完成时绝不能是 done。"""
    assert Supervisor.to_task_status("completed") is TaskStatus.done
    assert Supervisor.to_task_status("partial") is TaskStatus.partial
    assert Supervisor.to_task_status("cancelled") is TaskStatus.cancelled
    assert Supervisor.to_task_status("failed") is TaskStatus.failed
    # 未知状态兜底到 partial，绝不静默升级为 done
    assert Supervisor.to_task_status("running") is TaskStatus.partial


def test_blackboard_observe_excludes_worker_reasoning():
    """上下文隔离：主控看到的观察里不能混入 worker 的推理过程。"""
    bb = Blackboard(["amazon"])
    obs = bb.observe()
    # observe 只暴露结构化状态，不含任何 prompt / 推理文本字段
    assert set(obs) == {
        "goal", "status", "understanding_ready", "platforms",
        "open_issues", "actions_done", "last_actions", "elapsed",
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
