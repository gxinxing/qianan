"""单位经济测算 Agent — 调用 economics skill 计算 5 平台盈亏分析。"""
from __future__ import annotations

from skills.economics.skill_impl import EconomicsSkill


def create(config: dict | None = None) -> EconomicsSkill:
    """工厂函数：DHC 按此签名创建 Agent 实例。"""
    return EconomicsSkill(config=config)


__all__ = ["EconomicsSkill", "create"]
