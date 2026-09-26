"""Agent 动态感知与自进化架构测试。

测试关键能力：
1. Agent 动态市场感知（竞品差评反切 + A9/SEO 词策略）
2. 动态任务队列与 Worker 竞选/分配
3. 自进化反思与经验蒸馏闭环 (Evolution Agent -> Memory Store)
"""
from __future__ import annotations

from typing import Any

from app import memory_store
from app.agents.evolution import EvolutionAgent
from app.agents.swarm.blackboard import Blackboard
from app.agents.swarm.supervisor import Supervisor
from app.schemas import ComplianceIssue, GenerateRequest, PlatformListing


class FakeBailian:
    is_mock = True
    supports_vision = False

    async def acreate(self, **kwargs) -> Any:
        return None

    def chat(self, *args, **kwargs) -> Any:
        return ""

    def chat_with_tools(self, *args, **kwargs) -> Any:
        return {}

    def image_gen(self, *args, **kwargs) -> Any:
        return ""

    def vision(self, *args, **kwargs) -> Any:
        return {}


def _mock_req() -> GenerateRequest:
    return GenerateRequest(
        product_name="便携式榨汁杯",
        selling_points="USB-C 充电，高颜值，不漏水",
        category="home_kitchen",
        platforms=["amazon", "shopee"],
    )


# ------------------------------------------------ 1. 动态感知与防范打磨


def test_market_sensing_defensive_strategy():
    """验证 Agent 能否基于品类自动感知抗性与竞品风险，生成防御性策略。"""
    bb = Blackboard(["amazon", "shopee"])
    sup = Supervisor(FakeBailian(), bb)

    # 模拟感知步骤
    strategy = sup.sense_market_context(_mock_req())
    assert "amazon" in strategy
    assert "shopee" in strategy
    assert len(strategy["amazon"]["top_complaints"]) > 0
    assert "leakage" in strategy["amazon"]["top_complaints"] or "battery" in strategy["amazon"]["top_complaints"]
    assert "defensive_angles" in strategy["amazon"]


# ------------------------------------------------ 2. Worker 竞选与自主任务分配


def test_worker_bidding_and_assignment():
    """验证 Supervisor 能够评估平台特性并进行 Worker 动态调度分发。"""
    bb = Blackboard(["amazon", "shopee"])
    sup = Supervisor(FakeBailian(), bb)

    # Amazon Worker 竞选评估
    amz_bid = sup.evaluate_worker_fitness("amazon", "copy")
    shp_bid = sup.evaluate_worker_fitness("shopee", "copy")

    assert amz_bid["score"] > 0.8
    assert any("A9" in cap for cap in amz_bid["capabilities"])
    assert shp_bid["score"] > 0.8


# ------------------------------------------------ 3. 自进化与经验蒸馏闭环


def test_evolution_agent_distill_lessons():
    """验证 Evolution Agent 在任务结束后蒸馏教训并回写记忆库。"""
    req = _mock_req()
    bb = Blackboard(["amazon"])

    # 构建包含修补历史的列表
    listing = PlatformListing(
        platform="amazon",
        display_name="Amazon US",
        title="Portable Blender for Shake",
        bullets=["[NO LEAKAGE] Sealed silicon ring"],
        description="Detailed description",
        images=["http://img/main.jpg"],
        compliance=[
            ComplianceIssue(check_id="rule_001", severity="warn", field="bullets", message="建议避免绝对化用语")
        ]
    )

    # 进化 Agent 进行闭环蒸馏
    evo_agent = EvolutionAgent()
    lessons = evo_agent.distill_experience(req, [listing], bb.action_history)

    assert len(lessons) > 0
    lesson = lessons[0]
    assert lesson.platform == "amazon"
    assert "bullets" in lesson.lesson or "NO LEAKAGE" in lesson.lesson or "合规" in lesson.lesson

    # 存储并召回验证
    memory_store.remember(lesson.platform, req.category, lesson.lesson, source_task=bb.project_id)
    recalled = memory_store.recall("amazon", req.category, k=10)
    assert len(recalled) > 0
    assert any(r.get("source_task") == bb.project_id for r in recalled)
