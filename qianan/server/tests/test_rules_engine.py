"""规则引擎 Agent（app/agents/rules_engine.py）纯逻辑测试：约束清单 + prompt 摘要。"""
from __future__ import annotations

from app.agents.rules_engine import RulesEngineAgent
from app.rules_store import load_rules


def test_run_returns_rules_for_each_requested_platform():
    """run() 按请求平台返回对应规则库，不请求的平台不出现。"""
    result = RulesEngineAgent().run(["amazon", "shopee"])
    assert set(result) == {"amazon", "shopee"}
    assert result["amazon"]["title"]["maxLength"] == 200
    assert result["shopee"]["title"]["maxLength"] == 120


def test_constraint_brief_summarizes_limits_and_banned_words():
    """constraint_brief() 把规则压成自然语言约束：长度上限/五点数量/禁词全部出现。"""
    amazon = RulesEngineAgent.constraint_brief(load_rules("amazon"))
    assert "≤200" in amazon  # 标题上限
    assert "五点描述 5 条" in amazon  # bullets 数量约束（style != none 才输出）
    assert "描述 ≤3000" in amazon  # 描述上限
    assert "禁止使用以下词语" in amazon
    assert "free shipping" in amazon  # promotional 组代表性禁词

    # Shopee 无五点描述形态（style=none）：摘要不应出现五点约束，但保留标题上限
    shopee = RulesEngineAgent.constraint_brief(load_rules("shopee"))
    assert "五点描述" not in shopee
    assert "≤120" in shopee
