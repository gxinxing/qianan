"""输入理解②「意图」的纯逻辑测试（Step 3 最小切片）。

覆盖三层：
1. 意图 → 动作空间（`actions_for_goal` / `excluded_actions`）—— 意图改变执行图的机制；
2. 意图与规划联合消费（`resolve_skip` 的 `allowed` 裁剪）—— 两者证据分开记；
3. 意图 Agent 的判定与兜底（未写诉求不调模型、未知 goal 回退、平台白名单过滤）。

不触网：判定路径用 FakeClient 喂固定 JSON。
"""
from __future__ import annotations

import asyncio

from app.agents.intent import IntentAgent, describe
from app.orchestrator import excluded_actions, resolve_skip
from app.schemas import (
    ALL_ACTIONS,
    ALL_GOALS,
    GOAL_FULL_PACKAGE,
    GOAL_PREVIEW,
    GenerateRequest,
    Intent,
    actions_for_goal,
)


class FakeClient:
    """只实现意图判定用到的接口；`chat` 被调用时会记录次数。"""

    is_mock = False
    supports_vision = False

    def __init__(self, reply: str = "{}", boom: bool = False) -> None:
        self.reply = reply
        self.boom = boom
        self.calls = 0

    def chat(self, system: str, user: str, model: str | None = None) -> str:
        self.calls += 1
        if self.boom:
            raise RuntimeError("网关挂了")
        return self.reply


class MockClient(FakeClient):
    is_mock = True


def _run(req: GenerateRequest, client) -> Intent:
    return asyncio.run(IntentAgent(client).run(req))


def test_action_space_partition_by_goal():
    """完整包 = 全量动作；方案预览 = 只读懂商品 + 匹配规则；未知意图按完整包兜底。"""
    assert actions_for_goal(GOAL_FULL_PACKAGE) == set(ALL_ACTIONS)
    assert actions_for_goal(GOAL_PREVIEW) == {"understand_product", "match_rules"}
    assert actions_for_goal("不存在的意图") == set(ALL_ACTIONS)


def test_excluded_actions_is_the_intent_evidence():
    """excluded_actions 是「意图改变执行图」的直接证据：预览排除全部生成与合规动作。"""
    assert excluded_actions(GOAL_FULL_PACKAGE) == []
    ex = excluded_actions(GOAL_PREVIEW)
    assert set(ex) == set(ALL_ACTIONS) - {"understand_product", "match_rules"}
    assert "generate_visual" in ex and "audit_compliance" in ex
    # 顺序稳定（按 ALL_ACTIONS 排），便于前端与留痕对照
    assert ex == [a for a in ALL_ACTIONS if a in set(ex)]


def test_resolve_skip_is_clipped_by_intent_space():
    """规划声明的跳过项若不在本次意图的动作空间内，不算「跳过」（两者证据分开）。"""
    plan = {"skip": ["generate_video", "generate_detail_shots"]}
    # 完整包：两个都在空间内 → 都被消费
    assert resolve_skip(plan, None, actions_for_goal(GOAL_FULL_PACKAGE)) == [
        "generate_detail_shots",
        "generate_video",
    ]
    # 方案预览：这两个动作本就不进执行图 → 规划跳过项为空
    assert resolve_skip(plan, None, actions_for_goal(GOAL_PREVIEW)) == []
    # 不传 allowed（向后兼容 Step 1 的调用方式）→ 行为不变
    assert resolve_skip(plan, None) == ["generate_detail_shots", "generate_video"]


def test_no_request_text_skips_the_model_entirely():
    """未写诉求 = 默认完整包，**一次模型都不调**（绝大多数请求零额外延迟与成本）。"""
    client = FakeClient()
    intent = _run(GenerateRequest(product_name="杯子"), client)
    assert client.calls == 0
    assert intent.goal == GOAL_FULL_PACKAGE and intent.decided_by == "default"
    assert intent.platforms == []


def test_planner_verdict_is_parsed_and_whitelisted():
    """模型判定：preview + 平台从自然语言抽取，且非白名单平台被丢弃。"""
    client = FakeClient(
        '{"goal":"preview","platforms":["shopee","amazon","taobao"],'
        '"summary":"卖家想先看方案","confidence":0.9}'
    )
    intent = _run(GenerateRequest(request_text="先别生成，我想看看方案"), client)
    assert client.calls == 1
    assert intent.goal == GOAL_PREVIEW
    assert intent.platforms == ["shopee", "amazon"]  # taobao 不在白名单 → 丢弃
    assert intent.summary == "卖家想先看方案"
    assert intent.decided_by == "planner"
    assert describe(intent) == "先出方案，暂不生成 · 仅 2 个平台（诉求中指定）"


def test_unknown_goal_and_gateway_failure_fall_back_to_full_package():
    """兜底铁律：判定失败一律回退「出完整上架包」，绝不静默降级到更少的产出。"""
    # goal 不在枚举内 → 回完整包
    ok = _run(GenerateRequest(request_text="随便"), FakeClient('{"goal":"删库跑路","platforms":[]}'))
    assert ok.goal == GOAL_FULL_PACKAGE and ok.goal in ALL_GOALS

    # 网关异常 → 回完整包，且不抛出（否则整条任务会被意图判定拖死）
    boom = FakeClient(boom=True)
    fb = _run(GenerateRequest(request_text="先看方案"), boom)
    assert fb.goal == GOAL_FULL_PACKAGE and fb.decided_by == "fallback"

    # 模型输出不是 JSON → 同样回完整包
    bad = _run(GenerateRequest(request_text="先看方案"), FakeClient("我看不懂你在说什么"))
    assert bad.goal == GOAL_FULL_PACKAGE and bad.decided_by == "fallback"

    # mock 客户端（无 key 联调）→ 回完整包，不依赖模型
    mk = MockClient()
    m = _run(GenerateRequest(request_text="先看方案"), mk)
    assert m.goal == GOAL_FULL_PACKAGE and m.decided_by == "fallback" and mk.calls == 0


def test_intent_defaults_are_backward_compatible():
    """新增字段默认值不改变既有请求语义（task.intent 缺省 = 完整包）。"""
    it = Intent()
    assert it.goal == GOAL_FULL_PACKAGE
    assert it.platforms == [] and it.excluded_actions == []
    assert it.decided_by == "planner"

    req = GenerateRequest()
    assert req.request_text == ""  # 旧客户端不传该字段也能正常请求
