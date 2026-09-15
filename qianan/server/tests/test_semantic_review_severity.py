"""语义审核严重度分级 —— 防「无事实支撑的夸大」把 Agent 拖进无限修订循环。

回归背景（2026-09-15 实测）：
语义审核曾把所有问题一律标成 severity="error"，而 system prompt 规定
「有 error 必须调用 revise_listing 修订」。但其中一类问题**没有收敛点** ——
"事实档案没提到，文案却写成卖点"（如档案未提电机参数，文案写"高扭矩电机"）。
每轮改掉一批，文案又会带出新的具体表述被判同类问题，于是模型永远改不完：
实测 Amazon 单平台空转 11 轮、耗尽 300s 墙钟预算、**图片 0 张、视频 0 个**，
最后只能以 partial 收场。

这里锁住分级契约：
  - contradiction（与事实档案直接矛盾）→ error（阻断，必须改）
  - unsupported（证据不足）            → warn（提示，不该触发修订）
  - 缺失/未知 type                     → warn（fail-safe：宁可少阻断，也不要死循环）
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.agents.review import _SEVERITY_BY_TYPE, review_listing
from app.schemas import PlatformListing, Understanding


class _FakeClient:
    """只回放固定 JSON，不联网。"""

    is_mock = False

    def __init__(self, payload: str | dict) -> None:
        self._payload = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        self.calls = 0

    def chat(self, system: str, user: str, model: str | None = None) -> str:
        self.calls += 1
        return self._payload


def _listing() -> PlatformListing:
    return PlatformListing(
        platform="amazon",
        display_name="Amazon",
        title="Portable Blender 350ml",
        bullets=["USB rechargeable"],
        description="desc",
        images=["http://img/main.jpg"],
    )


def _understanding() -> Understanding:
    return Understanding(category="home_kitchen", product_type="portable blender")


def _issues(items: list[dict]) -> list:
    return asyncio.run(review_listing(_FakeClient({"issues": items}), _listing(), _understanding()))


# ----------------------------------------------------------- 分级契约


def test_contradiction_is_blocking_error():
    """与事实档案直接矛盾 = 硬伤，必须阻断。"""
    out = _issues([{"field": "material", "type": "contradiction", "message": "档案是涤纶，文案写纯棉"}])
    assert len(out) == 1
    assert out[0].severity == "error"


def test_unsupported_claim_is_only_warn():
    """「档案没写」只是证据不足，不是事实错误，绝不能阻断 —— 否则必死循环。"""
    out = _issues([{"field": "bullets[0]", "type": "unsupported", "message": "档案未提电机，文案写高扭矩电机"}])
    assert len(out) == 1
    assert out[0].severity == "warn"


def test_unknown_or_missing_type_falls_back_to_warn():
    """模型漏给/写错 type 时按 warn 处理：宁可少阻断，也不要让 Agent 卡死。"""
    out = _issues([
        {"field": "title", "message": "无 type 字段"},
        {"field": "description", "type": "something_weird", "message": "未知类型"},
    ])
    assert [i.severity for i in out] == ["warn", "warn"]


def test_type_matching_is_case_and_space_insensitive():
    """模型偶尔会把 type 写成 'Contradiction' 或带空格，仍要认出来。"""
    out = _issues([{"field": "title", "type": "  Contradiction ", "message": "格式不规整"}])
    assert out[0].severity == "error"


def test_message_keeps_type_for_traceability():
    """问题描述里保留 type，便于交付摘要与排查时区分来源。"""
    out = _issues([{"field": "bullets[1]", "type": "unsupported", "message": "无依据的碎冰宣称"}])
    assert "unsupported" in out[0].message
    assert out[0].check_id == "semantic_review"


# ----------------------------------------------------------- 健壮性


def test_both_types_in_one_pass_are_split_correctly():
    """一次审核同时报两类问题时，只有矛盾项阻断。"""
    out = _issues([
        {"field": "title", "type": "contradiction", "message": "容量写错"},
        {"field": "bullets[0]", "type": "unsupported", "message": "未提供支撑"},
        {"field": "bullets[1]", "type": "unsupported", "message": "未提供支撑"},
    ])
    assert [i.severity for i in out] == ["error", "warn", "warn"]


def test_no_issues_returns_empty():
    """干净文案不应产生任何问题，避免无端触发修订。"""
    assert _issues([]) == []


def test_garbage_output_never_raises():
    """模型输出不是 JSON / 空串时静默返回空列表 —— 审核失败不该炸掉整条生成。"""
    for bad in ["完全不是 json", "", "```json\n"]:
        assert asyncio.run(review_listing(_FakeClient(bad), _listing(), _understanding())) == []


def test_mock_client_skips_semantic_review():
    """Mock 模式不做语义审核（否则演示链路会被假数据判出一堆问题）。"""

    class _Mock:
        is_mock = True

        def chat(self, *a, **k):  # pragma: no cover - 不应被调用
            raise AssertionError("Mock 模式不应发起语义审核调用")

    assert asyncio.run(review_listing(_Mock(), _listing(), _understanding())) == []


def test_severity_map_covers_exactly_two_blocking_semantics():
    """分级表本身是契约：只有 contradiction 阻断。改动此表必须是有意为之。"""
    assert _SEVERITY_BY_TYPE == {"contradiction": "error", "unsupported": "warn"}
    assert sum(1 for v in _SEVERITY_BY_TYPE.values() if v == "error") == 1
