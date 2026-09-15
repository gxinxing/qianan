"""run_pipeline 交付闸门验收（对应审计发现 #3：流水线未过新闸门，缺图仍标 done）。

此前 run_pipeline 在视觉生成失败（被捕获并续跑）后仍直接置 TaskStatus.done，
于是「缺主图 / 仍有阻断级问题」的产物也会在 UI 上显示「完成」——典型的假完成。
本测试把联网组件换成确定性替身，直接驱动 run_pipeline，断言：

  A. 视觉生成失败（listing 缺主图）→ 闸门不过 → status == partial（绝不 done）
  B. 视觉生成成功（listing 有主图）→ 闸门通过 → status == done

编排层只验证「闸门是否诚实翻转状态」，不被模型/网络抖动干扰。
"""
from __future__ import annotations

import asyncio

import pytest

import app.agents.reflection as reflection_mod
import app.orchestrator as orch
from app.bailian.client import MockBailianClient
from app.agents.compliance import ComplianceAgent
from app.agents.copywriting import CopywritingAgent
from app.agents.intent import GOAL_FULL_PACKAGE, Intent, IntentAgent
from app.agents.understanding import ProductUnderstandingAgent
from app.agents.visual import VisualAgent
from app.orchestrator import run_pipeline
from app.schemas import GenerateRequest, TaskRecord, TaskStatus


# ------------------------------------------------------------ 确定性替身


class FakeIntent(IntentAgent):
    async def run(self, req):  # noqa: ANN001
        return Intent(goal=GOAL_FULL_PACKAGE, decided_by="default")


class FakeUnderstanding(ProductUnderstandingAgent):
    async def run(self, req, image_ref=None):  # noqa: ANN001
        return self._mock(req)


class _CopyMixin:
    async def run(self, req, understanding, platform, rules, focus="", memories=None):  # noqa: ANN001
        listing = self._mock(req, understanding, platform, rules, rules.get("locales", ["en-US"]))
        listing.platform = platform
        listing.display_name = rules.get("displayName", platform)
        if not listing.bullets:
            listing.bullets = ["Fast charge", "Easy to clean"]
        return listing


class FakeCopyNoImage(_CopyMixin, CopywritingAgent):
    """模拟视觉生成失败：文案有，但主图为空（闸门应据此判缺图）。"""


class FakeCopyWithImage(_CopyMixin, CopywritingAgent):
    """模拟视觉生成成功：补齐主图。"""

    async def run(self, req, understanding, platform, rules, focus="", memories=None):  # noqa: ANN001
        listing = await super().run(req, understanding, platform, rules, focus, memories)
        listing.images = ["http://img/main.jpg"]
        return listing


class FailingVisual(VisualAgent):
    async def run(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("视觉生成失败（模拟网关超时）")

    async def run_detail_shots(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("x")

    async def run_video(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("x")


class NoopVisual(VisualAgent):
    async def run(self, understanding, listing, rules, image_ref):  # noqa: ANN001
        listing.images = ["http://img/main.jpg"]

    async def run_detail_shots(self, understanding, listing, image_ref):  # noqa: ANN001
        listing.detail_images = ["http://img/d1.jpg"]

    async def run_video(self, understanding, listing):  # noqa: ANN001
        listing.video_url = "http://img/v.mp4"


class NoopCompliance:
    def run(self, listing, rules, category):  # noqa: ANN001
        return None


async def _noop_review(client, listing, understanding):  # noqa: ANN001
    return []


async def _async_noop(*args, **kwargs):  # noqa: ANN001
    return None


async def _default_plan(*args, **kwargs):  # noqa: ANN001
    return {"heal_budget": 1, "focus": "", "strategy": "default"}


# ------------------------------------------------------------ 夹具


def _install_stubs(monkeypatch, copy_cls, visual_cls) -> None:
    monkeypatch.setattr(orch, "IntentAgent", FakeIntent)
    monkeypatch.setattr(orch, "plan_task", _default_plan)
    monkeypatch.setattr(orch, "ProductUnderstandingAgent", FakeUnderstanding)
    monkeypatch.setattr(orch, "CopywritingAgent", copy_cls)
    monkeypatch.setattr(orch, "VisualAgent", visual_cls)
    monkeypatch.setattr(orch, "ComplianceAgent", NoopCompliance)
    monkeypatch.setattr(orch, "review_listing", _noop_review)
    monkeypatch.setattr(orch, "_generate_strategy_report", _async_noop)
    monkeypatch.setattr(reflection_mod, "self_reflect", _async_noop)


def _make_task(platforms: list[str]) -> TaskRecord:
    req = GenerateRequest(
        product_name="Portable Blender 380ml",
        selling_points="USB-C fast charge; easy to clean",
        category="home_kitchen",
        platforms=platforms,
    )
    return TaskRecord(task_id="test-pipe-tid", request=req)


# ------------------------------------------------------------ 测试


def test_run_pipeline_missing_image_is_partial(monkeypatch):
    """视觉生成失败 → 缺主图 → 闸门不过 → 绝不标 done。"""
    _install_stubs(monkeypatch, FakeCopyNoImage, FailingVisual)
    task = _make_task(["amazon", "shopee"])
    asyncio.run(run_pipeline(task, MockBailianClient()))
    assert task.status != TaskStatus.done, "缺主图绝不能标 done"
    assert task.status == TaskStatus.partial, f"应降为 partial，实际 {task.status}"
    assert task.error and "主图" in task.error, f"应说明缺主图，实际 {task.error}"


def test_run_pipeline_with_image_is_done(monkeypatch):
    """视觉生成成功 → 主图齐全 → 闸门通过 → done。"""
    _install_stubs(monkeypatch, FakeCopyWithImage, NoopVisual)
    task = _make_task(["amazon", "shopee"])
    asyncio.run(run_pipeline(task, MockBailianClient()))
    assert task.status == TaskStatus.done, f"产物齐备应 done，实际 {task.status}（{task.error}）"
    assert task.error is None
