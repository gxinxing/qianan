"""文案生成 Agent — 调用 copywriting skill 生成多平台 Listing 文案。"""
from __future__ import annotations

from skills.copywriting.skill_impl import CopywritingSkill


def create(config: dict | None = None) -> CopywritingSkill:
    """工厂函数：DHC 按此签名创建 Agent 实例。"""
    return CopywritingSkill(config=config)


__all__ = ["CopywritingSkill", "create"]
