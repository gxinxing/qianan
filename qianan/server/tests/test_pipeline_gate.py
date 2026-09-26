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

import app.agents.reflection as reflection_mod
import app.orchestrator as orch
from app.agents.copywriting import CopywritingAgent
from app.agents.intent import GOAL_FULL_PACKAGE, Intent, IntentAgent
from app.agents.understanding import ProductUnderstandingAgent
from app.agents.visual import VisualAgent
from app.bailian.client import MockBailianClient
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


# ------------------------------------------------------------ 生图解耦：mock 文本 + 真实图


class _MockTextRealImageClient(MockBailianClient):
    """模拟云端降级拓扑：文本链路已降级 mock（is_mock=True），但生图走独立网关仍真实。

    对应 _ResilientClient 文本降级后的真实形态：is_mock=True 且 image_live=True
    （独立生图网关与文本降级解耦；MockBailianClient 本身无 image_live 属性，
    必须显式暴露才能走真实生图分支）。
    """

    image_live = True

    def image_gen(self, prompt, model=None, ref_image=None):
        return "https://getapib.org/real-image-task.png"


def test_pipeline_mock_text_real_image(monkeypatch):
    """mock 文本 + image_live 生图：pipeline 全流程走完，产物图片为真实 URL、终态 done。

    这是云端「文本欠费降级 + apimart 生图真实」拓扑的核心保障 ——
    生图判定不能因文本 is_mock 而走 mock:// 占位图。
    """
    from app.agents.visual import VisualAgent

    class _RealVisual(VisualAgent):
        """用真实 VisualAgent 逻辑（不 stub run），走 _image_live 判定分支。"""

        pass

    _install_stubs(monkeypatch, FakeCopyWithImage, NoopVisual)
    # 覆写回真实 VisualAgent，只让文案/理解保持确定性替身
    monkeypatch.setattr(orch, "VisualAgent", _RealVisual)

    client = _MockTextRealImageClient()
    task = _make_task(["amazon"])
    asyncio.run(run_pipeline(task, client))

    assert task.status == TaskStatus.done, f"应 done，实际 {task.status}（{task.error}）"
    urls = [str(u) for u in task.listings[0].images]
    assert urls, "产物应有主图"
    assert all(not u.startswith("mock://") for u in urls), (
        f"生图不应因文本降级变 mock 占位图，实际 {urls}"
    )
    assert any("real-image-task" in u for u in urls), f"应包含独立网关真实出图，实际 {urls}"
