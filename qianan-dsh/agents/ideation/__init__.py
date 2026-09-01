"""选品灵感 Agent — 调用 ideation skill 生成数据驱动选品建议。"""
from __future__ import annotations

from skills.ideation.skill_impl import IdeationSkill


def create(config: dict | None = None) -> IdeationSkill:
    """工厂函数：DHC 按此签名创建 Agent 实例。"""
    return IdeationSkill(config=config)


__all__ = ["IdeationSkill", "create"]
