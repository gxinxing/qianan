"""规划跳过项（Step 1：让「规划」真正改变执行图）的纯逻辑测试。

覆盖两层：
1. policy 层 `filter_skip_request`：强制动作不可被跳过（硬约束，不依赖 prompt 自律）；
2. 执行层 `resolve_skip`：把规划声明解析为实际生效的跳过列表，并支持验证通道 force_skip。

端到端"真跳过"的证据由真实服务跑批验证（见 docs/12 与验证脚本），
此处只保证决策逻辑本身确定、无副作用。
"""
from __future__ import annotations

from app.orchestrator import _default_plan, filter_skip_request, resolve_skip
from app.schemas import (
    ACTION_LABELS,
    ALL_ACTIONS,
    FORCED_ACTIONS,
    OPTIONAL_ACTIONS,
    AblationConfig,
    TaskPlan,
)


def test_action_space_is_partitioned_and_labelled():
    """动作空间自洽：可选与强制不重叠，且每个动作都有中文名（留痕可读）。"""
    assert set(OPTIONAL_ACTIONS) & set(FORCED_ACTIONS) == set()
    assert set(ALL_ACTIONS) == set(OPTIONAL_ACTIONS) | set(FORCED_ACTIONS)
    assert set(ACTION_LABELS) == set(ALL_ACTIONS)


def test_filter_skip_request_accepts_optional_only():
    """policy：可选动作被接受，强制动作一律拒绝；两者可在同一次请求里共存。"""
    accepted, refused = filter_skip_request(
        ["generate_video", "audit_compliance", "understand_product"]
    )
    assert accepted == ["generate_video"]
    assert refused == ["audit_compliance", "understand_product"]


def test_filter_skip_request_tolerates_dirty_input():
    """policy：空值 / None / 非字符串 / 带空白的输入不应炸，且结果去重有序。"""
    assert filter_skip_request(None) == ([], [])
    assert filter_skip_request([]) == ([], [])
    assert filter_skip_request(["", "   "]) == ([], [])
    assert filter_skip_request([" generate_video "]) == (["generate_video"], [])
    accepted, _ = filter_skip_request(
        ["generate_video", "generate_detail_shots", "generate_video"]
    )
    assert accepted == ["generate_detail_shots", "generate_video"]  # 去重 + 按 OPTIONAL 顺序


def test_resolve_skip_reads_plan_declaration():
    """执行层：规划声明的 skip 被解析为生效列表；非法项被静默丢弃。"""
    plan = {"skip": ["generate_video", "audit_compliance"]}
    assert resolve_skip(plan, None) == ["generate_video"]


def test_resolve_skip_force_channel_overrides_planner():
    """验证通道：force_skip 优先于规划声明，且同样受 policy 过滤（强制动作跳不掉）。"""
    abl = AblationConfig(force_skip=["generate_detail_shots", "audit_compliance"])
    plan = {"skip": ["generate_video"]}
    assert resolve_skip(plan, abl) == ["generate_detail_shots"]

    # force_skip 为空时不生效，回落到规划声明
    assert resolve_skip(plan, AblationConfig()) == ["generate_video"]


def test_default_plan_declares_no_skip_and_model_defaults_are_clean():
    """默认计划不跳过任何步骤；新增字段默认空值，保证旧客户端与旧持久化数据兼容。"""
    assert _default_plan()["skip"] == []

    plan = TaskPlan()
    assert plan.skip == []
    assert plan.skipped_actions == []
    assert AblationConfig().force_skip == []

    # 跳过项与生效项分离：模型声明 skip 不代表执行器已消费（两者可对照取证）
    p = TaskPlan(decided_by="planner", skip=["generate_video"], skipped_actions=[])
    assert p.skip == ["generate_video"] and p.skipped_actions == []
