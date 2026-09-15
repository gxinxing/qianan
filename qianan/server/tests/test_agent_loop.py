"""Agent 闭环验收测试（对应 P0「增加 4 条 Agent 验收测试」）。

现有 23→49 条测试只证明**组件**正确（交付闸门纯函数、工具循环取消、蜂群黑板）。
这 4 条真正驱动 `run_chat_agent` 主循环（function calling tool loop + 工具 handler），
证明「Agent 闭环」在端到端层面成立 —— 也就是评委现场最容易击穿的「假完成」问题：

  1. 模型提前提交 → 被拒，状态绝不变 done
  2. 工具循环超限 → 不显示成功（status 不是 done，done 事件也不宣称完成）
  3. 某平台未审核 → 不能交付（submit_deliverable 被闸门挡下）
  4. 全部平台审核通过 → 才能 complete（status = done）

实现方式：用脚本客户端（is_mock=False，按脚本返回 tool_calls）驱动真实工具循环，
并把三个联网 agent + 语义审核 + 反思替换成确定性替身 —— 这样测试只验证**编排层**
（submit_deliverable 是否真被闸门卡住、状态映射是否诚实），不被模型/网络抖动干扰。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

import app.agents.reflection as reflection_mod
import app.chat_agent as chat_agent
from app.chat_agent import run_chat_agent
from app.agents.compliance import ComplianceAgent
from app.agents.copywriting import CopywritingAgent
from app.agents.understanding import ProductUnderstandingAgent
from app.agents.visual import VisualAgent
from app.schemas import (
    ComplianceIssue,
    GenerateRequest,
    PlatformListing,
    TaskRecord,
    TaskStatus,
    Understanding,
)


# ------------------------------------------------------------ 脚本客户端


class ScriptedClient:
    """按脚本返回 tool_calls 的假客户端，模拟「模型在循环里的选择」。

    is_mock=False —— 否则 run_chat_agent 会短路到 run_pipeline，根本不进工具循环。
    script 是 [(工具名, platform|None), ...]；用尽后若给了 repeat 则一直重复该项。
    """

    is_mock = False

    def __init__(self, script: list[tuple[str, str | None]] | None = None, repeat: tuple[str, str | None] | None = None) -> None:
        self.script = list(script or [])
        self.repeat = repeat
        self.calls = 0

    def chat_with_tools(self, messages: list[dict], schemas: list[dict]) -> dict:
        self.calls += 1
        if self.script:
            steps = [self.script.pop(0)]
        elif self.repeat:
            steps = [self.repeat]
        else:
            return {"content": "收敛", "tool_calls": []}
        calls = []
        for i, (name, platform) in enumerate(steps):
            args = {"platform": platform} if platform is not None else {}
            calls.append({"id": f"c{i}", "function": {"name": name, "arguments": json.dumps(args)}})
        return {"content": "", "tool_calls": calls}


# ------------------------------------------------------------ 确定性替身


class FakeUnderstanding(ProductUnderstandingAgent):
    async def run(self, req: GenerateRequest, image_ref: str | None = None) -> Understanding:
        return self._mock(req)


class FakeCopy(CopywritingAgent):
    async def run(self, req, understanding, platform, rules, focus="", memories=None) -> PlatformListing:
        listing = self._mock(req, understanding, platform, rules, rules.get("locales", ["en-US"]))
        # _mock 不保证产出主图/五点（取决于各平台规则字段），闸门要求这两样齐全才算可上架；
        # 这里补齐，让正向用例能构造出「产物齐备」的 listing，不把规则差异带进闭环断言。
        if not listing.images:
            listing.images = ["http://img/main.jpg"]
        if not listing.bullets:
            listing.bullets = ["Fast charge", "Easy to clean"]
        return listing

    async def revise(self, listing, rules, errors) -> PlatformListing:  # noqa: ANN001
        return listing


class NoopVisual(VisualAgent):
    async def run(self, understanding, listing, rules, image_ref):  # noqa: ANN001
        if not listing.images:
            listing.images = ["http://img/main.jpg"]

    async def run_detail_shots(self, understanding, listing, image_ref):  # noqa: ANN001
        listing.detail_images = ["http://img/d1.jpg"]

    async def run_video(self, understanding, listing):  # noqa: ANN001
        listing.video_url = "http://img/v.mp4"


class NoopCompliance:
    """规则引擎确定性替身：不改 listing.compliance，让编排层测试不被规则抖动干扰。

    合规引擎本身的拦截能力由 test_delivery_gate.py 的闸门纯函数覆盖；这里只验证
    submit_deliverable 是否依据「已审核 + 产物完整」正确翻转状态。
    """

    def run(self, listing, rules, category) -> None:  # noqa: ANN001
        return None


async def _fake_review_listing(client, listing, understanding) -> list:  # noqa: ANN001
    return []


async def _async_noop(*args, **kwargs) -> None:  # noqa: ANN001
    return None


# ------------------------------------------------------------ 测试夹具


def _install_stubs(monkeypatch) -> None:
    """把联网组件换成确定性替身，让 run_chat_agent 真正跑工具循环但不发网络请求。"""
    monkeypatch.setattr(chat_agent, "ProductUnderstandingAgent", FakeUnderstanding)
    monkeypatch.setattr(chat_agent, "CopywritingAgent", FakeCopy)
    monkeypatch.setattr(chat_agent, "VisualAgent", NoopVisual)
    monkeypatch.setattr(chat_agent, "ComplianceAgent", NoopCompliance)
    monkeypatch.setattr(chat_agent, "review_listing", _fake_review_listing)
    # submit_deliverable 会调 self_reflect（真实路径走模型）；这里是 noop，避免联网/死循环
    monkeypatch.setattr(reflection_mod, "self_reflect", _async_noop)


def _make_task(platforms: list[str]) -> TaskRecord:
    req = GenerateRequest(
        product_name="Portable Blender 380ml",
        selling_points="USB-C fast charge; easy to clean",
        category="home_kitchen",
        platforms=platforms,
    )
    return TaskRecord(task_id="test-loop-tid", request=req)


def _capture_events(task: TaskRecord):
    """捕获 SSE 事件；镜像 main.py 的 SSE 包装，让 done 事件带上 task.status，便于断言。

    run_chat_agent 推 done 时给的是 summary 字符串，status 字段由 main.py 在外层补；
    这里用 task.status 补同样字段，使「done 事件是否如实宣称完成」可被直接断言。
    返回 (事件列表, on_event 闭包) —— 两者都要用。
    """
    events: list[tuple[str, Any]] = []

    def on_event(evt_type: str, content):
        if evt_type == "done":
            events.append(("done", {"status": task.status.value, "summary": content}))
        else:
            events.append((evt_type, content))

    return events, on_event


def _done_events_status(events: list[tuple[str, Any]]) -> list[str]:
    return [c.get("status") for (t, c) in events if t == "done" and isinstance(c, dict)]


def _text_events(events: list[tuple[str, Any]]) -> list[str]:
    return [c for (t, c) in events if t == "text" and isinstance(c, str)]


# ----------------------------------------------------- 验收 1：提前提交被拒


def test_agent_rejects_early_submit(monkeypatch):
    """验收 1：模型第一步就 submit_deliverable（什么都没生成）→ 必须被拒，status 绝不变 done。

    这是「假完成」最直接的反例：此前只要 listings 非空就标 done，而这里 listings 空，
    更要紧的是即便生成了部分、没过闸门也绝不能宣称完成。
    """
    _install_stubs(monkeypatch)
    task = _make_task(["amazon", "shopee"])
    # 只生成了 amazon 就提交（shopee 没生成、amazon 没审核）→ 典型的「提前 finish」
    client = ScriptedClient(
        script=[
            ("understand_product", None),
            ("generate_listing", "amazon"),
            ("submit_deliverable", None),
        ]
    )
    events, on_event = _capture_events(task)

    asyncio.run(run_chat_agent(task, client, "帮我上架", on_event=on_event))

    assert task.status != TaskStatus.done, "提前提交绝不能标 done"
    assert task.status in (TaskStatus.partial, TaskStatus.running, TaskStatus.failed)
    # 闸门必须明确回绝、且把话术回给模型（不要向用户谎称完成）
    joined = " ".join(_text_events(events))
    assert "不要向用户宣称已完成" in joined or "还不能交付" in joined


# --------------------------------------------- 验收 2：循环超限不显示成功


def test_agent_loop_over_limit_does_not_show_success(monkeypatch):
    """验收 2：工具循环超过最大轮数仍不收敛 → 不能显示成功。

    落点：run_tool_loop 返回 fallback=True，run_chat_agent 把它映射成 partial/failed，
    绝不是 done；且推给前端的 done 事件 status 字段也绝不是 "done"。
    """
    _install_stubs(monkeypatch)
    monkeypatch.setattr(chat_agent, "CHAT_MAX_ROUNDS", 4)  # 收紧轮数，让超限立刻触发
    task = _make_task(["amazon"])
    # 生成了一个平台后就反复 understand_product，永远不收敛、不提交
    client = ScriptedClient(
        script=[("understand_product", None), ("generate_listing", "amazon")],
        repeat=("understand_product", None),
    )
    events, on_event = _capture_events(task)

    asyncio.run(run_chat_agent(task, client, "帮我上架", on_event=on_event))

    assert task.status != TaskStatus.done, "超轮数未收敛绝不能标 done"
    # 前端据此判断「成功」的 done 事件，status 绝不可能是 "done"
    assert "done" not in _done_events_status(events), "done 事件不能谎称完成"
    assert task.status in (TaskStatus.partial, TaskStatus.failed)


# --------------------------------------------- 验收 3：未审核平台不能交付


def test_agent_blocks_delivery_when_platform_unreviewed(monkeypatch):
    """验收 3：amazon 已审核、shopee 没审核就 submit → 闸门挡下，status != done。

    对应评委最关心的「勾了 5 个只做出 2 个却显示完整上架包」的弱化版：
    哪怕只差一个平台的审核，整个交付也不成立。
    """
    _install_stubs(monkeypatch)
    task = _make_task(["amazon", "shopee"])
    client = ScriptedClient(
        script=[
            ("understand_product", None),
            ("generate_listing", "amazon"),
            ("review_listing", "amazon"),
            ("generate_listing", "shopee"),
            # 注意：shopee 没有 review_listing
            ("submit_deliverable", None),
        ]
    )
    events, on_event = _capture_events(task)

    asyncio.run(run_chat_agent(task, client, "帮我上架", on_event=on_event))

    assert task.status != TaskStatus.done, "有平台未审核绝不能交付"
    joined = " ".join(_text_events(events))
    assert "尚未通过审核" in joined or "不要向用户宣称已完成" in joined


# --------------------------------------------- 验收 4：全部审核通过才完成


def test_agent_completes_only_when_all_platforms_reviewed(monkeypatch):
    """验收 4：两个平台都生成 + 都审核 → submit_deliverable 过闸门 → status = done。

    这是闭环成立的「正向」证据：reviewed 集合与产物齐全时，done 是唯一诚实的结果。
    """
    _install_stubs(monkeypatch)
    task = _make_task(["amazon", "shopee"])
    client = ScriptedClient(
        script=[
            ("understand_product", None),
            ("generate_listing", "amazon"),
            ("review_listing", "amazon"),
            ("generate_listing", "shopee"),
            ("review_listing", "shopee"),
            ("submit_deliverable", None),
        ]
    )
    events, on_event = _capture_events(task)

    asyncio.run(run_chat_agent(task, client, "帮我上架", on_event=on_event))

    assert task.status == TaskStatus.done, "全部平台生成+审核后应通过闸门并标 done"
    assert _done_events_status(events) == ["done"], "完成事件的 status 必须如实为 done"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
