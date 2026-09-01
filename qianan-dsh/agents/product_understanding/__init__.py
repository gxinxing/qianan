"""商品理解 Agent — 调用 product-understanding skill 结构化解析商品信息。"""
from __future__ import annotations

from skills.product_understanding.skill_impl import ProductUnderstandingSkill


def create(config: dict | None = None) -> ProductUnderstandingSkill:
    """工厂函数：DHC 按此签名创建 Agent 实例。"""
    return ProductUnderstandingSkill(config=config)


__all__ = ["ProductUnderstandingSkill", "create"]
