"""规则引擎 Agent — 调用 rules-engine skill 加载平台规则并提取约束清单。"""
from __future__ import annotations

from skills.rules_engine.skill_impl import RulesEngineSkill


def create(config: dict | None = None) -> RulesEngineSkill:
    """工厂函数：DHC 按此签名创建 Agent 实例。"""
    return RulesEngineSkill(config=config)


__all__ = ["RulesEngineSkill", "create"]
