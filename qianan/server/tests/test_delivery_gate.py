"""交付闸门与「完成可信度」的纯逻辑测试。

对应外部审计的验收标准：
  3. 模型提前 finish 会被 policy 拒绝
  4. 工具超时后不会显示「完成」
  6. 审核后修改文案会自动使审核状态失效

这些不变量一旦回退，UI 上的「完成」就不可信 —— 所以锁在这里。
"""
from __future__ import annotations

import pytest

from app.chat_agent import IMAGE_ONLY_FIELDS, evaluate_delivery_gate
from app.schemas import ComplianceIssue, PlatformListing, TaskStatus


def _listing(
    platform: str,
    *,
    title: str = "Portable Blender 380ml",
    bullets: list[str] | None = None,
    images: list[str] | None = None,
    issues: list[ComplianceIssue] | None = None,
    reviewed_ok: bool = True,
) -> PlatformListing:
    """构造一个 listing；默认构造出来是「完全达标」的。"""
    return PlatformListing(
        platform=platform,
        display_name=platform.upper(),
        title=title,
        bullets=bullets if bullets is not None else ["Fast charge", "Easy clean"],
        description="desc",
        images=images if images is not None else ["http://img/main.jpg"],
        compliance=issues or [],
    )


def _err(field: str, message: str = "bad") -> ComplianceIssue:
    return ComplianceIssue(check_id=f"chk_{field}", field=field, message=message, severity="error")


def _warn(field: str) -> ComplianceIssue:
    return ComplianceIssue(check_id=f"chk_{field}", field=field, message="note", severity="warn")


# ---------------------------------------------------------------- 闸门：放行


def test_gate_passes_when_all_platforms_complete():
    """全平台齐全 + 已审核 → 放行。"""
    listings = {
        "amazon": _listing("amazon"),
        "shopee": _listing("shopee"),
    }
    gate = evaluate_delivery_gate(["amazon", "shopee"], listings, {"amazon", "shopee"})
    assert gate["ok"] is True
    assert gate["blockers"] == []
    assert sorted(gate["covered"]) == ["amazon", "shopee"]


# ------------------------------------------------------- 闸门：验收标准 3


def test_gate_blocks_missing_platform():
    """验收 3：勾了 5 个只做出 2 个 → 拒绝 finish（此前会宣称「完整上架包」）。"""
    listings = {"amazon": _listing("amazon"), "shopee": _listing("shopee")}
    gate = evaluate_delivery_gate(
        ["amazon", "shopee", "aliexpress", "lazada", "tiktokshop"],
        listings,
        {"amazon", "shopee"},
    )
    assert gate["ok"] is False
    assert len(gate["blockers"]) == 3  # 三个未生成的平台
    assert any("尚未生成任何内容" in b for b in gate["blockers"])
    # 已完成的平台仍要记入 covered，便于 UI 如实显示进度
    assert sorted(gate["covered"]) == ["amazon", "shopee"]


def test_gate_blocks_unreviewed_listing():
    """验收 3：产物未经审核 → 拒绝。"""
    listings = {"amazon": _listing("amazon")}
    gate = evaluate_delivery_gate(["amazon"], listings, reviewed=set())
    assert gate["ok"] is False
    assert "尚未通过审核" in gate["blockers"][0]


def test_gate_blocks_missing_required_artifacts():
    """验收 3：缺标题 / 缺五点 / 缺主图 → 拒绝，且三个问题都要报出来。"""
    listings = {"amazon": _listing("amazon", title="", bullets=[], images=[])}
    gate = evaluate_delivery_gate(["amazon"], listings, {"amazon"})
    assert gate["ok"] is False
    blocker = gate["blockers"][0]
    assert "缺标题" in blocker and "缺五点描述" in blocker and "缺主图" in blocker


def test_gate_blocks_hard_compliance_errors():
    """验收 3：存在阻断级 error → 拒绝。"""
    listings = {"amazon": _listing("amazon", issues=[_err("title"), _err("bullets")])}
    gate = evaluate_delivery_gate(["amazon"], listings, {"amazon"})
    assert gate["ok"] is False
    assert "阻断级问题" in gate["blockers"][0]
    assert "title" in gate["blockers"][0]


def test_gate_ignores_image_only_errors_to_avoid_revise_deadlock():
    """mainImage 类问题靠出图解决；若纳入闸门，模型会反复 revise 直到超轮数。

    这里把它排除，改由「缺主图」这一条覆盖：有图就放行，没图就拦。
    """
    assert "mainImage" in IMAGE_ONLY_FIELDS
    # 有 mainImage error 但确实有主图 → 放行（不该逼模型去改文案）
    with_img = _listing("amazon", images=["http://img/main.jpg"], issues=[_err("mainImage")])
    assert evaluate_delivery_gate(["amazon"], {"amazon": with_img}, {"amazon"})["ok"] is True

    # 没有主图 → 由「缺主图」拦住
    no_img = _listing("amazon", images=[], issues=[_err("mainImage")])
    gate = evaluate_delivery_gate(["amazon"], {"amazon": no_img}, {"amazon"})
    assert gate["ok"] is False
    assert "缺主图" in gate["blockers"][0]


def test_gate_warns_without_blocking():
    """提示项（warn / 缺详情图 / 缺视频）不阻断，但要如实披露。"""
    listings = {"amazon": _listing("amazon", issues=[_warn("title")])}
    gate = evaluate_delivery_gate(["amazon"], listings, {"amazon"})
    assert gate["ok"] is True
    assert any("提示" in w for w in gate["warnings"])
    assert any("详情图" in w for w in gate["warnings"])


# ------------------------------------------------------- 验收标准 6：审核失效


def test_gate_blocks_when_listing_modified_after_review():
    """验收 6：审核通过后又被修改 → 审核结论失效，必须重新审核。

    这是由调用方（tool_revise）把平台移出 reviewed 集合实现的；
    闸门只负责据此拒绝 finish，两者配合才成立。
    """
    listings = {"amazon": _listing("amazon")}
    reviewed = {"amazon"}
    assert evaluate_delivery_gate(["amazon"], listings, reviewed)["ok"] is True

    reviewed.discard("amazon")  # tool_revise 在修订后做的事
    gate = evaluate_delivery_gate(["amazon"], listings, reviewed)
    assert gate["ok"] is False
    assert "审核" in gate["blockers"][0]


# --------------------------------------------------- 验收标准 4：状态语义


def test_partial_and_cancelled_statuses_exist():
    """验收 4：fallback / 取消必须能落到 done 以外的状态。"""
    assert TaskStatus.partial.value == "partial"
    assert TaskStatus.cancelled.value == "cancelled"
    # done 只能由闸门放行产生，不能是兜底默认值
    assert TaskStatus.done.value == "done"


def test_gate_is_pure_and_does_not_mutate_inputs():
    """闸门是纯函数：不修改传入的 listings / reviewed，便于单测与回放。"""
    listings = {"amazon": _listing("amazon")}
    reviewed = {"amazon"}
    before = dict(listings)
    evaluate_delivery_gate(["amazon"], listings, reviewed)
    assert listings == before
    assert reviewed == {"amazon"}


@pytest.mark.parametrize(
    "platforms,keys,reviewed,expected_ok",
    [
        (["amazon"], ["amazon"], {"amazon"}, True),
        (["amazon"], [], set(), False),          # 一个都没做
        (["amazon", "shopee"], ["amazon"], {"amazon"}, False),  # 少一个平台
        ([], [], set(), True),                   # 空请求：无平台即无要求
    ],
)
def test_gate_matrix(platforms, keys, reviewed, expected_ok):
    listings = {k: _listing(k) for k in keys}
    assert evaluate_delivery_gate(platforms, listings, reviewed)["ok"] is expected_ok


# --------------------------------------------------- 验收标准 5：真取消


class _FakeClient:
    """最小替身：每次都返回一个 noop 工具调用，模拟「模型想继续干活」。"""

    is_mock = True

    def __init__(self):
        self.calls = 0

    def chat_with_tools(self, messages, schemas):
        self.calls += 1
        if self.calls >= 2:  # 第二次起收敛，避免测试死循环
            return {"content": "done", "tool_calls": []}
        return {
            "content": "",
            "tool_calls": [{"id": "1", "function": {"name": "noop", "arguments": "{}"}}],
        }


def _noop_tool() -> "ToolSpec":
    from app.agent_core.registry import ToolSpec

    async def handler() -> str:
        return "ok"

    return ToolSpec(
        name="noop",
        description="noop",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=handler,
    )


def test_run_tool_loop_stops_immediately_when_cancelled():
    """验收 5：取消信号必须在**下一个检查点**生效，不再发起新的模型调用。

    此前「停止」只断开前端 fetch，后台循环会一直跑到 max_rounds 或超时。
    """
    import asyncio

    from app.agent_core.loop import run_tool_loop

    client = _FakeClient()
    already_stopped = lambda: True  # noqa: E731

    result = asyncio.run(
        run_tool_loop(client, "sys", "user", [_noop_tool()], max_rounds=10,
                      deadline_s=30, should_stop=already_stopped)
    )
    assert result["cancelled"] is True
    assert result["reason"] == "用户取消"
    assert client.calls == 0, "取消后不应再发起任何模型调用"


def test_run_tool_loop_returns_cancelled_flag_not_fallback():
    """取消 ≠ 失败：调用方据此把状态置为 cancelled，而不是 failed 或 done。"""
    import asyncio

    from app.agent_core.loop import run_tool_loop

    client = _FakeClient()
    assert asyncio.run(
        run_tool_loop(client, "sys", "user", [_noop_tool()], should_stop=lambda: True)
    ) == {
        "content": None,
        "tool_results": {},
        "rounds": 0,
        "fallback": False,   # 取消不是未收敛
        "reason": "用户取消",
        "cancelled": True,
    }


def test_run_tool_loop_normal_run_is_not_cancelled():
    """回归保护：没有取消信号时行为不变，cancelled 保持 False。"""
    import asyncio

    from app.agent_core.loop import run_tool_loop

    client = _FakeClient()
    result = asyncio.run(
        run_tool_loop(client, "sys", "user", [_noop_tool()], max_rounds=5, deadline_s=30)
    )
    assert result["cancelled"] is False
    assert result["fallback"] is False
