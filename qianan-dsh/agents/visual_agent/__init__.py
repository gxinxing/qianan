"""视觉生成 Agent — 调用 visual-agent skill 生成符合平台规范的商品主图。"""
from __future__ import annotations

from skills.visual_agent.skill_impl import VisualAgentSkill


def create(config: dict | None = None) -> VisualAgentSkill:
    """工厂函数：DHC 按此签名创建 Agent 实例。"""
    return VisualAgentSkill(config=config)


__all__ = ["VisualAgentSkill", "create"]
